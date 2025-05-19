import json
from template import PAYWALL_TEMPLATE

def get_paywall_html(
        amount: float,
        testnet: str,
        payment_requirments: 'PaymentRequirements',
        current_url: str,
) -> str:
    """
    Returns the HTML for the paywall page.
    """

    # Define the chain configuration as a Python dictionary
    chain_config = {
        "84532": {
            "usdcAddress": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
            "usdcName": "USDC"
        }
    }

    # Create the configuration script to inject
    config_script = f"""
    <script>
        window.x402 = {{
            amount: {amount},
            paymentRequirements: {payment_requirments.model_dump_json()},
            testnet: "{testnet}",
            currentUrl: "{current_url}",
            config: {{
                "chainConfig": {json.dumps(chain_config)},
            }}
        }};
        console.log('Payment details initialized:', window.x402);
    </script>
    """
    # Inject the configuration script into the head
    return PAYWALL_TEMPLATE.replace("</head>", f"{config_script}\n</head>")