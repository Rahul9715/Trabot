from pydantic import BaseModel, Field
from typing import Literal

class Approval(BaseModel):
    session_id: str = Field(min_length=8, max_length=80)
    symbols: list[str]
    max_risk_per_trade: float = Field(gt=0, le=50)
    max_daily_loss: float = Field(gt=0)
    max_trades: int = Field(ge=1, le=2)
    expires_at: str

class Signal(BaseModel):
    signal_id: str = Field(min_length=8, max_length=80)
    symbol: str
    instrument_token: str
    side: Literal["BUY", "SELL"]
    entry: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    target: float = Field(gt=0)
    quantity: int = Field(gt=0)
    product: Literal["D", "I"] = "D"
    rationale: str = ""
    confidence: float = Field(default=0, ge=0, le=100)
    target_rationale: str = ""
    stop_loss_rationale: str = ""
    evidence: dict = Field(default_factory=dict)

class ResearchRequest(BaseModel):
    market_context: str = Field(min_length=20, max_length=15000)
    question: str = "Identify market regime, risks, sectors to watch and conditional trade setups. Do not invent prices or claim certainty."


class CandidateDecision(BaseModel):
    decision: Literal["APPROVED", "REJECTED", "WATCHLIST"]
    reason: str = Field(default="", max_length=4000)

class Candidate(BaseModel):
    candidate_id: str = Field(min_length=8, max_length=80)
    symbol: str
    instrument_token: str
    side: Literal["BUY", "SELL"]
    entry: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    target: float = Field(gt=0)
    confidence: float = Field(ge=0, le=100)
    rationale: str = Field(min_length=1, max_length=12000)
    target_rationale: str = ""
    stop_loss_rationale: str = ""
    evidence: dict = Field(default_factory=dict)
    strategy_version: str = "unversioned"
    review_1: dict = Field(default_factory=dict)
    review_2: dict = Field(default_factory=dict)


class TradeUpdate(BaseModel):
    actual_entry: float | None = Field(default=None, gt=0)
    actual_stop_loss: float | None = Field(default=None, gt=0)
    actual_target: float | None = Field(default=None, gt=0)
    actual_exit: float | None = Field(default=None, gt=0)
    charges: float = Field(default=0, ge=0)
    exit_reason: str = Field(default="", max_length=2000)
