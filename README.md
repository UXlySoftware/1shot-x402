# Implementing x402 with 1Shot and FastAPI

[x402](https://www.x402.org/) is a payment standard proposed by Coinbase for letting API services charge for access by piggybacking on top of the
existing [HTTP 402](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/402) status code. Specifically, x402 enables API customers,
particularly AI agents, to pay for and gain access to premium API resources via blockchain-based value transfers. 

There are 4 primary actors in the x402 scheme:

1. **The Client**: This is the entity attempting to read or utilize an API with valuable resources
2. **The Resource Server**: The Resource Server is the actor who is serving paid content in exchange for money
3. **A Facilitator**: This is a logical role which could also be filled by the same person running the API server, but could also the a dedicated 3rd party. The purpose of the facilitator is to read and write to the blockchain network. [1Shot API](https://1shotapi.com) makes it trivial to build your own facilitator with FastAPI.
4. **The Blockchain**: This is the settlement network where the digital asset is deployed that is being accepted as payment, like [USDC](https://basescan.org/token/0x833589fcd6edb6e08f4c7c32d4f71b54bda02913#code) which implements [EIP-3009](https://eips.ethereum.org/EIPS/eip-3009).

![x402 Sequence Diagram](./x402-protocol-flow.png)