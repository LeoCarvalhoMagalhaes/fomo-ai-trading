"""Redes negociadas pela FOMO e seus identificadores em cada provedor (verificados em 31/10/2026)."""
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class Chain(StrEnum):
    solana = "solana"
    base = "base"
    bsc = "bsc"
    ethereum = "ethereum"
    monad = "monad"
    robinhood = "robinhood"


@dataclass(frozen=True)
class ChainInfo:
    label: str
    gecko_id: str
    dex_id: str
    goplus_id: str
    family: Literal["svm", "evm"]
    default_gas_usd: float


CHAINS: dict[Chain, ChainInfo] = {
    Chain.solana: ChainInfo("Solana", "solana", "solana", "solana", "svm", 0.01),
    Chain.base: ChainInfo("Base", "base", "base", "8453", "evm", 0.02),
    Chain.bsc: ChainInfo("BNB Chain", "bsc", "bsc", "56", "evm", 0.05),
    Chain.ethereum: ChainInfo("Ethereum", "eth", "ethereum", "1", "evm", 1.50),
    Chain.monad: ChainInfo("Monad", "monad", "monad", "143", "evm", 0.02),
    Chain.robinhood: ChainInfo("Robinhood Chain", "robinhood", "robinhood", "4663", "evm", 0.02),
}

_BY_DEX = {info.dex_id: chain for chain, info in CHAINS.items()}
_BY_GECKO = {info.gecko_id: chain for chain, info in CHAINS.items()}


def chain_from_dex(dex_id: str) -> Chain | None:
    return _BY_DEX.get(dex_id)


def chain_from_gecko(gecko_id: str) -> Chain | None:
    return _BY_GECKO.get(gecko_id)
