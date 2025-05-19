import base64
import json
import logging
from enum import Enum
from typing import List, Optional, Dict, Any

from oneshot import (
    oneshot_client,
    BUSINESS_ID
)

from pydantic import (
    BaseModel, 
    Field, 
    field_validator,
    model_validator,
    ValidationError
)
from fastapi import (
    HTTPException, 
    Header
)

logger = logging.getLogger(__name__)

from fastapi.responses import HTMLResponse
from paywall_html import get_paywall_html

# Constants
EVM_ADDRESS_REGEX = r"^0x[0-9a-fA-F]{40}$"
MIXED_ADDRESS_REGEX = r"^0x[a-fA-F0-9]{40}|[A-Za-z0-9][A-Za-z0-9-]{0,34}[A-Za-z0-9]$"
HEX_ENCODED_64_BYTE_REGEX = r"^0x[0-9a-fA-F]{64}$"
EVM_SIGNATURE_REGEX = r"^0x[0-9a-fA-F]{130}$"

# Helper validators
def is_integer(value: str) -> bool:
    return value.isdigit() and int(value) >= 0

def has_max_length(value: str, max_length: int) -> bool:
    return len(value) <= max_length

class SupportedNetworks(Enum):
    BASE_SEPOLIA = "base-sepolia"
    BASE = "base"
    AVALANCHE_FUJI = "avalanche-fuji"
    AVALANCHE = "avalanche"

class X402Versions(Enum):
    V1 = 1

class ErrorReasons(Enum):
    INSUFFICIENT_FUNDS = "insufficient_funds"
    INVALID_SCHEME = "invalid_scheme"
    INVALID_NETWORK = "invalid_network"

class PaymentSchemes(Enum):
    EXACT = "exact"

class Extra(BaseModel):
    name: str
    version: str

# x402PaymentRequirements
class PaymentRequirements(BaseModel):
    scheme: PaymentSchemes
    network: SupportedNetworks  
    maxAmountRequired: str
    resource: str = Field(..., pattern=r"https?://[^\s/$.?#].[^\s]*$")
    description: str
    mimeType: Optional[str] = None
    outputSchema: Optional[Dict[str, Any]] = None
    payTo: str = Field(..., pattern=MIXED_ADDRESS_REGEX)
    maxTimeoutSeconds: int
    asset: str = Field(..., pattern=MIXED_ADDRESS_REGEX)
    extra: Optional[Extra] = None

    @field_validator("maxAmountRequired")
    def validate_max_amount(cls, value):
        if not is_integer(value):
            raise ValueError("maxAmountRequired must be an integer.")
        return value

# x402ExactEvmPayload
class ExactEvmPayloadAuthorization(BaseModel):
    from_: str = Field(..., pattern=EVM_ADDRESS_REGEX, alias="from")
    to: str = Field(..., pattern=EVM_ADDRESS_REGEX)
    value: str
    validAfter: str
    validBefore: str
    nonce: str = Field(..., pattern=HEX_ENCODED_64_BYTE_REGEX)

    @model_validator(mode="after")
    def validate_values(cls, model):
        if not (is_integer(model.value) and has_max_length(model.value, 18)):
            raise ValueError("value must be an integer with a maximum length of 18.")
        if not is_integer(model.validAfter):
            raise ValueError("validAfter must be an integer.")
        if not is_integer(model.validBefore):
            raise ValueError("validBefore must be an integer.")
        if not int(model.validAfter) < int(model.validBefore):
            raise ValueError("validAfter must be less than validBefore.")
        return model

class ExactEvmPayload(BaseModel):
    signature: str = Field(..., pattern=EVM_SIGNATURE_REGEX)
    authorization: ExactEvmPayloadAuthorization

# x402PaymentPayload
class PaymentPayload(BaseModel):
    x402Version: X402Versions
    scheme: PaymentSchemes
    network: str  # Replace with the actual NetworkSchema type if available
    payload: ExactEvmPayload

class UnsignedPaymentPayload(BaseModel):
    x402Version: int
    scheme: PaymentSchemes
    network: str  # Replace with the actual NetworkSchema type if available
    payload: Dict[str, Any]  # Payload without the signature

# x402VerifyResponse
class VerifyResponse(BaseModel):
    isValid: bool
    invalidReason: Optional[ErrorReasons]
    payer: Optional[str] = Field(None, pattern=MIXED_ADDRESS_REGEX)

# x402SettleResponse
class SettleResponse(BaseModel):
    success: bool
    errorReason: Optional[ErrorReasons]
    payer: Optional[str] = Field(None, pattern=MIXED_ADDRESS_REGEX)
    transaction: str = Field(..., pattern=MIXED_ADDRESS_REGEX)
    network: str  # Replace with the actual NetworkSchema type if available

# x402SupportedPaymentKind
class SupportedPaymentKind(BaseModel):
    x402Version: X402Versions
    scheme: PaymentSchemes
    network: str  # Replace with the actual NetworkSchema type if available

# x402SupportedPaymentKindsResponse
class SupportedPaymentKindsResponse(BaseModel):
    kinds: List[SupportedPaymentKind]

# Define a premium dependency for x402 payment verification
class X402PaymentVerifier:
    def __init__(
            self, 
            network: int, 
            pay_to_address: str, 
            payment_asset: str,
            asset_name: str,
            premium_cost: int, 
            resource: str, 
            resource_description: str,
            eip712_version: str = "2",
        ):
        self.payment_requirements = PaymentRequirements(
            scheme=PaymentSchemes.EXACT,
            network=SupportedNetworks(network),
            maxAmountRequired=str(premium_cost),
            resource=resource,
            description=resource_description,
            payTo=pay_to_address,
            maxTimeoutSeconds=60,
            asset=payment_asset,
            extra={
                "name": asset_name, 
                "version": eip712_version
                }
        )

    async def __call__(
            self, 
            x_payment: str = Header(None),
            user_agent: str = Header(None),
            accept: str = Header(None)
    ):
        if not x_payment:
            if "text/html" in accept and "Mozilla" in user_agent:
                # Return an HTML response for web browsers
                html_content = get_paywall_html(
                    amount=0.05,
                    testnet=self.payment_requirements.network.value,
                    payment_requirments=self.payment_requirements,
                    current_url=self.payment_requirements.resource,  # Replace with the actual URL
                )
                return HTMLResponse(content=html_content, status_code=402)
            else:
                raise HTTPException(
                    status_code=402,
                    detail={
                        "x402Version": X402Versions.V1.value,
                        "error": "X-PAYMENT header is required.",
                        "accepts": self.payment_requirements.model_dump_json()
                    }
            )
        
        # Example: Extract payment metadata from the header
        try:
            payment_data = self.decode_payment(x_payment)
            logger.info(f"Decoded payment data: {payment_data}")
        except ValueError as e:
            raise HTTPException(
                status_code=402,
                detail=f"Invalid payment data: {str(e)}"
            )

        # Validate the payment using Coinbase API
        is_valid = await self.verify(payment_data)
        if not is_valid:
            raise HTTPException(status_code=402, detail="Payment verification failed.")
        
        return {"message": "Payment verified"}

    def decode_payment(self, payment: str) -> PaymentPayload:
        """
        Decodes a base64-encoded payment string, parses it as JSON, and validates it against the PaymentPayload model.

        Args:
            payment (str): The base64-encoded payment string.

        Returns:
            PaymentPayload: The validated PaymentPayload object.

        Raises:
            ValueError: If decoding, parsing, or validation fails.
        """
        try:
            # Decode the base64-encoded string
            decoded = base64.b64decode(payment)

            # Parse the JSON string into a dictionary
            parsed = json.loads(decoded)

            # Validate the object against the PaymentPayload model
            validated = PaymentPayload(**parsed)
            return validated
        except (base64.binascii.Error, json.JSONDecodeError) as e:
            raise ValueError("Failed to decode or parse the payment string.") from e
        except ValidationError as e:
            raise ValueError("Validation failed for the payment payload.") from e

    async def verify(self, payment_data: PaymentPayload) -> bool:
        # Use 1Shot API to verify payment details and submit the payment transaction
        logger.info(f"Validating payment: {payment_data}")
        transaction_endpoints = await oneshot_client.transactions.list(
            business_id=BUSINESS_ID,
            params={"chain_id": "84532", "name": "Base Sepolia USDC transferWithAuthorization"}
        )
        test_result = await oneshot_client.transactions.test(
            transaction_id=transaction_endpoints.response[0].id,
            params={
                "from": payment_data.payload.authorization.from_,
                "to": payment_data.payload.authorization.to,
                "value": payment_data.payload.authorization.value,
                "validAfter": payment_data.payload.authorization.validAfter,
                "validBefore": payment_data.payload.authorization.validBefore,
                "nonce": payment_data.payload.authorization.nonce,
                "signature": payment_data.payload.signature
            }
        )
        return test_result.success