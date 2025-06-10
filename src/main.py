import os
import logging
from contextlib import asynccontextmanager
from typing import Tuple

from fastapi import (
    FastAPI, 
    Request, 
    HTTPException, 
    Depends,
)
from fastapi.responses import HTMLResponse, RedirectResponse

from x402 import (
    X402PaymentVerifier,
    PaymentRequirements
)

from paywall_html import get_paywall_html

# import the helper verification function from the uxly_1shot_client package
from uxly_1shot_client import verify_webhook

# we import the async 1Shot client from the oneshot.py file as a singleton
from oneshot import oneshot_client, BUSINESS_ID

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# read our static url from the environment
HOST_URL = os.getenv("TUNNEL_BASE_URL")

# read the desired token and price for our api from the environment
RECIPIENT_ADDRESS = str(os.getenv("RECIPIENT_ADDRESS"))
PAYMENT_TOKEN_ADDRESS = str(os.getenv("PAYMENT_TOKEN_ADDRESS"))
MAX_AMOUNT_REQUIRED = str(os.getenv("MAX_AMOUNT_REQUIRED"))

# example of a wrapper class to handle webhook verification with FastAPI
# rather than looking up the public key from 1Shot API each time, you could store it in a database or cache
class webhookAuthenticator:
    def __init__(self):
        logger.info("Webhook Authenticator initialized.")

    async def __call__(self, request: Request):
        try:
            # Extract the required fields from the request
            body = await request.json()  # Raw request body
            signature = body.pop("signature", None)  # Pop the signature field from the body

            if not signature:
                raise HTTPException(status_code=400, detail="Signature field missing")
            
            # look up the contract method that generated the callback and get the public key
            # in a production application, store the public key in a database or cache for faster access
            contract_method = await oneshot_client.contract_methods.get(
                contract_method_id=body["data"]["transactionId"],
            )

            if not contract_method.public_key:
                raise HTTPException(status_code=400, detail="Public key not found")

            # Verify the signature with the public key you stored corresponding to the contract method
            is_valid = verify_webhook(
                body=body,
                signature=signature,
                public_key=contract_method.public_key
            )

            if not is_valid:
                raise HTTPException(status_code=403, detail="Invalid signature")
        except Exception as e:
            logger.error(f"Error verifying webhook: {e}")
            raise HTTPException(status_code=500, detail=f"Internal error: {e}")

# for convenience, we are going to automatically create a contract method endpoint when we start the FastAPI server.
# on restarts, we will check if the endpoint exists and if it does, we will skip creating it
# this will save us the hassle of having to create it manually
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event to check for or create a demo 1Shot API transaction endpoint."""
    # lets start by checking that we have an escrow wallet provisioned for our account on the Sepolia network
    # if not we will exit since we must have one to continue
    wallets = await oneshot_client.wallets.list(BUSINESS_ID, {"chain_id": "84532"})
    if not ((len(wallets.response) >= 1) and (float(wallets.response[0].account_balance_details.balance) > 0.00001)):
        raise RuntimeError(
            "Escrow wallet not provisioned or insufficient balance on the Base Sepolia network. "
            "Please ensure an escrow wallet exists and has sufficient funds by logging into https://app.1shotapi.dev/escrow-wallets."
        )
    else:
        logger.info("Escrow wallet is provisioned and has sufficient funds.")

    # to keep this demo self contained, we are going to check our 1Shot API account for an existing contract method for the 
    # USDC contract at 0x036cbd53842c5426634e7929541ec2318f3dcf7e on the Base Sepolia network, if we don't have one, we'll create it automatically
    # then we'll use that endpoint when people call our /premium route
    # for a more serious application you will probably create your required contract function endpoints ahead of time
    # and input their contract method ids as environment variables
    contract_methods = await oneshot_client.contract_methods.list(
        business_id=BUSINESS_ID,
        params={"chain_id": "84532", "name": "Base Sepolia USDC transferWithAuthorization"}
    )
    if len(contract_methods.response) == 0:
        logger.info("Creating new contract method endpoint for x402 demo.")
        endpoint_payload = {
            "chain_id": "84532",
            "contractAddress": "0x036cbd53842c5426634e7929541ec2318f3dcf7e",
            "walletId": wallets.response[0].id,
            "name": "Base Sepolia USDC transferWithAuthorization",
            "description": "This endpoint is used with the x402 API payment protocol.",
            "callbackUrl": f"{HOST_URL}/1shot", # this will register our ngrok static url as the callback url for the transaction endpoint
            "stateMutability": "nonpayable",
            "functionName": "transferWithAuthorization",
            "inputs": [
                {
                    "name": "from",
                    "type": "address",
                    "index": 0,
                },
                {
                    "name": "to",
                    "type": "address",
                    "index": 1
                },
                {
                    "name": "value",
                    "type": "uint",
                    "index": 2
                },
                {
                    "name": "validAfter",
                    "type": "uint",
                    "index": 3
                },
                {
                    "name": "validBefore",
                    "type": "uint",
                    "index": 4
                },
                {
                    "name": "nonce",
                    "type": "bytes",
                    "typeSize": 32,
                    "index": 5
                },
                {
                    "name": "signature",
                    "type": "bytes",
                    "index": 6
                }
            ],
            "outputs": []
        }
        contract_method = await oneshot_client.contract_methods.create(
            business_id=BUSINESS_ID,
            params=endpoint_payload
        )
    else:
        logger.info(f"Transaction endpoint already exists, skipping creation.")

    yield

# create the FastAPI app and register the lifespan event
app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root_redirect():
    """
    Redirects the root URL ('/') to the '/premium' endpoint.
    """
    return RedirectResponse(url="/premium")

# this is our premium access endpoint that must be paid for to receive the resource
@app.get("/premium")
async def premium_endpoint(
    request: Request,
    settled: Tuple[bool, PaymentRequirements] = Depends(
        X402PaymentVerifier(
            network="base-sepolia",
            pay_to_address=RECIPIENT_ADDRESS, 
            payment_asset=PAYMENT_TOKEN_ADDRESS,
            asset_name="USDC",
            max_amount_required=MAX_AMOUNT_REQUIRED,
            resource=HOST_URL + "/premium",
            resource_description="Pay in crypto for premium access to the resource"
            )
        )
):
    # For this demo, if the consumer is a human with a web browser, we will show them a paywall
    # where they can connect a wallet and pay for access
    if not settled[0]:
        html_content = get_paywall_html(
            amount=0.05, # this should match MAX_AMOUNT_REQUIRED but in dollars
            testnet="base-sepolia",
            payment_requirments=settled[1],
            current_url=HOST_URL + "/premium",  # Replace with the actual URL
        )
        return HTMLResponse(content=html_content, status_code=402)
    else:
        # Return the HTMLResponse with the embedded YouTube video
        return HTMLResponse(
            content='<iframe width="560" height="315" src="https://www.youtube.com/embed/dQw4w9WgXcQ" frameborder="0" allowfullscreen></iframe>',
            status_code=200
        )

# this is the route where we will receive and authenticate webhook callbacks from 1Shot
@app.post("/1shot", dependencies=[Depends(webhookAuthenticator())])
async def handle_python_webhook(request: Request):
    logger.info("Webhook received.")
    return {"message": "Webhook received and signature verified"}

@app.get('/healthcheck')
async def root():
    return {'message': 'x402 demo is up!'}
