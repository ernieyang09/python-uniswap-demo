import datetime
import decimal
import os
import sys
from decimal import Decimal

from dotenv import load_dotenv
from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_defi.confirmation import wait_transactions_to_complete
from eth_utils import event_abi_to_log_topic
from web3 import Web3
from web3.exceptions import TimeExhausted
from web3.middleware import construct_sign_and_send_raw_middleware

from contracts import fetch_erc20_details, get_contract

swap_event_abi = {
    "anonymous": False,
    "inputs": [
        {
            "indexed": True,
            "internalType": "address",
            "name": "sender",
            "type": "address",
        },
        {
            "indexed": True,
            "internalType": "address",
            "name": "recipient",
            "type": "address",
        },
        {
            "indexed": False,
            "internalType": "int256",
            "name": "amount0",
            "type": "int256",
        },
        {
            "indexed": False,
            "internalType": "int256",
            "name": "amount1",
            "type": "int256",
        },
        {
            "indexed": False,
            "internalType": "uint160",
            "name": "sqrtPriceX96",
            "type": "uint160",
        },
        {
            "indexed": False,
            "internalType": "uint128",
            "name": "liquidity",
            "type": "uint128",
        },
        {
            "indexed": False,
            "internalType": "int24",
            "name": "tick",
            "type": "int24",
        },
    ],
    "name": "Swap",
    "type": "event",
}

loaded = load_dotenv(override=True)

private_key = os.environ.get("PRIVATE_KEY")
swap_router_addr = Web3.to_checksum_address(os.environ.get("SWAP_ROUTER"))
qouter_addr = Web3.to_checksum_address(os.environ.get("QUOTER"))
quote_token_addr = Web3.to_checksum_address(os.environ.get("QUOTE_TOKEN"))
base_token_addr = Web3.to_checksum_address(os.environ.get("BASE_TOKEN"))


account: LocalAccount = Account.from_key(private_key)
my_address = account.address

json_rpc_url = os.environ.get("JSON_RPC")
web3 = Web3(Web3.HTTPProvider(json_rpc_url))

web3.middleware_onion.add(construct_sign_and_send_raw_middleware(account))

base = fetch_erc20_details(web3, base_token_addr)
quote = fetch_erc20_details(web3, quote_token_addr)

# change this
decimal_amount = Decimal(0.01)

router_v2 = get_contract(web3, swap_router_addr, "SwapRouterV2.json")
quoter_v2 = get_contract(web3, qouter_addr, "QuoterV2.json")

# # Convert a human-readable number to fixed decimal with 18 decimal places
raw_amount = quote.convert_to_raw(decimal_amount)


quote_amount = quoter_v2.functions.quoteExactInputSingle(
    (
        quote_token_addr,  # tokenIn
        base_token_addr,  # tokenOut
        raw_amount,  # amountIn (uint256)
        10000,  # fee (uint24)
        0,  # sqrtPriceLimitX96 (uint160)
    )
).call()[0]

# the usd amount you convert out
print(f"Quote amount: {quote_amount / 10 ** base.decimals}")

slippage_percentage = 5 / 100  # 0.5% slippage
slippage_adjusted_amount = quote_amount / (1 + slippage_percentage)


tx = router_v2.functions.exactInputSingle(
    (
        quote_token_addr,  # tokenIn
        base_token_addr,  # tokenOut
        10000,  # fee (uint24)
        my_address,  # recipient
        raw_amount,  # amountIn
        int(slippage_adjusted_amount),  # amountOutMinimum
        0,
    )
).build_transaction({"gas": 1_000_000, "from": my_address})


tx_hash = web3.eth.send_transaction(tx)


try:
    # Wait for the transaction to be mined with a specified timeout
    tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    # Check the transaction status
    if tx_receipt.status == 1:
        print(f"Transaction successful with hash: {tx_receipt.transactionHash.hex()}")
        # need to check the final amount out here.
        swap_event_signature = event_abi_to_log_topic(swap_event_abi)

        swap_event = next(
            (log for log in tx_receipt.logs if log.topics[0] == swap_event_signature),
            None,
        )

        if swap_event:
            decoded_event = web3.codec.decode(
                ["int256", "int256", "uint160", "uint128"],
                swap_event["data"],
            )

            # Determine the actual amount out
            amount_out = (
                decoded_event[0] if int(decoded_event[0]) < 0 else decoded_event[1]
            )

            print(f"Actual amount out: {abs(amount_out / 10 ** base.decimals)}")
        else:
            print("No Swap event found in the transaction logs.")

    else:
        raise Exception(
            f"Transaction failed with hash: {tx_receipt.transactionHash.hex()}"
        )

except TimeExhausted as e:
    print("Transaction was not mined within the timeout period.")
except Exception as e:
    print(f"An error occurred: {e}")
