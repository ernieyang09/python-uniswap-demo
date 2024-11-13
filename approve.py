import os

from dotenv import load_dotenv
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3
from web3.exceptions import TimeExhausted
from web3.middleware import construct_sign_and_send_raw_middleware

from contracts import fetch_erc20_details

load_dotenv()

private_key = os.environ.get("PRIVATE_KEY")
swap_router_addr = Web3.to_checksum_address(os.environ.get("SWAP_ROUTER"))
quote_token_addr = Web3.to_checksum_address(os.environ.get("QUOTE_TOKEN"))

account: LocalAccount = Account.from_key(private_key)
my_address = account.address

json_rpc_url = os.environ.get("JSON_RPC")
web3 = Web3(Web3.HTTPProvider(json_rpc_url))
web3.middleware_onion.add(construct_sign_and_send_raw_middleware(account))


quote = fetch_erc20_details(web3, quote_token_addr)
MAX_UINT256 = Web3.to_int(
    hexstr="0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
)
approve = quote.contract.functions.approve(swap_router_addr, MAX_UINT256)


tx = approve.build_transaction(
    {
        "gas": 85000,
        "from": my_address,
    }
)

try:
    tx_hash = web3.eth.send_transaction(tx)
    # Wait for the transaction to be mined with a specified timeout
    tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    # Check the transaction status
    if tx_receipt.status == 1:
        print(f"Transaction successful with hash: {tx_receipt.transactionHash.hex()}")
    else:
        raise Exception(
            f"Transaction failed with hash: {tx_receipt.transactionHash.hex()}"
        )

except TimeExhausted as e:
    print("Transaction was not mined within the timeout period.")
except Exception as e:
    print(f"An error occurred: {e}")
