from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, root_validator


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
    network: str  # Replace with the actual NetworkSchema type if available
    maxAmountRequired: str
    resource: str = Field(..., regex=r"https?://[^\s/$.?#].[^\s]*$")
    description: str
    mimeType: Optional[str] = None
    outputSchema: Optional[Dict[str, Any]] = None
    payTo: str = Field(..., regex=MIXED_ADDRESS_REGEX)
    maxTimeoutSeconds: int
    asset: str = Field(..., regex=MIXED_ADDRESS_REGEX)
    extra: Optional[Extra] = None

    @root_validator
    def validate_max_amount(cls, values):
        if not is_integer(values.get("maxAmountRequired", "")):
            raise ValueError("maxAmountRequired must be an integer.")
        return values

# x402ExactEvmPayload
class ExactEvmPayloadAuthorization(BaseModel):
    from_: str = Field(..., regex=EVM_ADDRESS_REGEX, alias="from")
    to: str = Field(..., regex=EVM_ADDRESS_REGEX)
    value: str
    validAfter: str
    validBefore: str
    nonce: str = Field(..., regex=HEX_ENCODED_64_BYTE_REGEX)

    @root_validator
    def validate_values(cls, values):
        value = values.get("value", "")
        if not (is_integer(value) and has_max_length(value, 18)):
            raise ValueError("value must be an integer with a maximum length of 18.")
        if not is_integer(values.get("validAfter", "")):
            raise ValueError("validAfter must be an integer.")
        if not is_integer(values.get("validBefore", "")):
            raise ValueError("validBefore must be an integer.")
        return values

class ExactEvmPayload(BaseModel):
    signature: str = Field(..., regex=EVM_SIGNATURE_REGEX)
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
    payer: Optional[str] = Field(None, regex=MIXED_ADDRESS_REGEX)

# x402SettleResponse
class SettleResponse(BaseModel):
    success: bool
    errorReason: Optional[ErrorReasons]
    payer: Optional[str] = Field(None, regex=MIXED_ADDRESS_REGEX)
    transaction: str = Field(..., regex=MIXED_ADDRESS_REGEX)
    network: str  # Replace with the actual NetworkSchema type if available

# x402SupportedPaymentKind
class SupportedPaymentKind(BaseModel):
    x402Version: X402Versions
    scheme: PaymentSchemes
    network: str  # Replace with the actual NetworkSchema type if available

# x402SupportedPaymentKindsResponse
class SupportedPaymentKindsResponse(BaseModel):
    kinds: List[SupportedPaymentKind]