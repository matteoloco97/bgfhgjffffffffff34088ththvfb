#!/usr/bin/env python3
"""
tests/test_betting_trading_agents.py
====================================

Unit tests per BettingAgent e TradingAgent.
Testa calcoli EV, Kelly, Position Size, Risk/Reward.
"""

import sys
import os
import pytest
import math

# Add project root to path dynamically
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

# Import moduli da testare
try:
    from agents.betting_agent import (
        calculate_ev,
        calculate_kelly,
        decimal_to_probability,
        american_to_decimal,
        extract_betting_params,
        is_betting_query,
    )
    from agents.trading_agent import (
        calculate_position_size,
        calculate_risk_reward,
        calculate_leverage_impact,
        calculate_compound_growth,
        extract_trading_params,
        is_trading_query,
    )
    IMPORTS_OK = True
except ImportError as e:
    print(f"Warning: Import failed: {e}")
    IMPORTS_OK = False


# ===================== BETTING AGENT TESTS =====================

class TestBettingCalculations:
    """Test per calcoli betting."""
    
    def test_decimal_to_probability(self):
        """Testa conversione quota → probabilità."""
        assert abs(decimal_to_probability(2.0) - 0.5) < 0.001
        assert abs(decimal_to_probability(4.0) - 0.25) < 0.001
        assert abs(decimal_to_probability(1.5) - 0.6667) < 0.01
        assert decimal_to_probability(0) == 0  # Edge case
    
    def test_american_to_decimal(self):
        """Testa conversione quote americane → decimali."""
        assert abs(american_to_decimal(100) - 2.0) < 0.001
        assert abs(american_to_decimal(200) - 3.0) < 0.001
        assert abs(american_to_decimal(-100) - 2.0) < 0.001
        assert abs(american_to_decimal(-200) - 1.5) < 0.001
    
    def test_ev_positive(self):
        """Testa EV positivo (value bet)."""
        result = calculate_ev(odds=2.50, probability=0.50, stake=100)
        
        assert result["is_value"] == True
        assert result["ev"] > 0
        # EV = (0.5 × 150) - (0.5 × 100) = 75 - 50 = 25
        assert abs(result["ev"] - 25) < 0.01
    
    def test_ev_negative(self):
        """Testa EV negativo (no value)."""
        result = calculate_ev(odds=2.00, probability=0.40, stake=100)
        
        assert result["is_value"] == False
        assert result["ev"] < 0
    
    def test_ev_breakeven(self):
        """Testa EV a zero (quota equa)."""
        result = calculate_ev(odds=2.00, probability=0.50, stake=100)
        
        assert abs(result["ev"]) < 0.01  # Circa 0
    
    def test_kelly_positive(self):
        """Testa Kelly positivo."""
        result = calculate_kelly(odds=2.50, probability=0.50)
        
        assert result["kelly_full"] > 0
        assert result["kelly_fraction"] > 0
        assert result["kelly_fraction"] < result["kelly_full"]  # Quarter Kelly
    
    def test_kelly_negative(self):
        """Testa Kelly negativo (no edge)."""
        result = calculate_kelly(odds=2.00, probability=0.40)
        
        assert result["kelly_full"] == 0
        assert "note" in result or result["kelly_full"] == 0
    
    def test_kelly_formula(self):
        """Verifica formula Kelly corretta."""
        # Kelly = (p × b - q) / b
        # Con odds=3.0, p=0.4: b=2.0, q=0.6
        # Kelly = (0.4 × 2 - 0.6) / 2 = (0.8 - 0.6) / 2 = 0.1 = 10%
        result = calculate_kelly(odds=3.0, probability=0.4)
        
        assert abs(result["kelly_full"] - 10.0) < 0.5


class TestBettingQueryParsing:
    """Test parsing query betting."""
    
    def test_extract_odds(self):
        """Testa estrazione quota."""
        params = extract_betting_params("calcola ev quota 2.50 prob 45%")
        
        assert "odds" in params
        assert abs(params["odds"] - 2.50) < 0.01
    
    def test_extract_probability(self):
        """Testa estrazione probabilità."""
        params = extract_betting_params("kelly quota 1.85 probabilità 60%")
        
        assert "probability" in params
        assert abs(params["probability"] - 0.60) < 0.01
    
    def test_is_betting_query(self):
        """Testa riconoscimento query betting."""
        assert is_betting_query("calcola ev scommessa") == True
        assert is_betting_query("kelly criterion") == True
        assert is_betting_query("value bet quota 2.1") == True
        assert is_betting_query("che tempo fa") == False


# ===================== TRADING AGENT TESTS =====================

class TestTradingCalculations:
    """Test per calcoli trading."""
    
    def test_position_size_long(self):
        """Testa position size per posizione long."""
        result = calculate_position_size(
            account_size=10000,
            risk_percent=2,
            entry_price=100,
            stop_loss_price=95,
        )
        
        assert "error" not in result
        assert result["direction"] == "LONG"
        assert result["risk_amount"] == 200  # 2% di 10000
        # Position = 200 / 5 = 40 unità
        assert abs(result["position_size_units"] - 40) < 0.01
    
    def test_position_size_short(self):
        """Testa position size per posizione short."""
        result = calculate_position_size(
            account_size=10000,
            risk_percent=2,
            entry_price=100,
            stop_loss_price=105,
        )
        
        assert "error" not in result
        assert result["direction"] == "SHORT"
    
    def test_risk_reward_long(self):
        """Testa calcolo R:R per long."""
        result = calculate_risk_reward(
            entry_price=100,
            stop_loss=95,
            take_profit=115,
        )
        
        assert "error" not in result
        assert result["direction"] == "LONG"
        assert result["risk"] == 5  # 100 - 95
        assert result["reward"] == 15  # 115 - 100
        assert result["rr_ratio"] == 3.0  # 15/5
    
    def test_risk_reward_short(self):
        """Testa calcolo R:R per short."""
        result = calculate_risk_reward(
            entry_price=100,
            stop_loss=105,
            take_profit=90,
        )
        
        assert "error" not in result
        assert result["direction"] == "SHORT"
        assert result["risk"] == 5  # 105 - 100
        assert result["reward"] == 10  # 100 - 90
        assert result["rr_ratio"] == 2.0  # 10/5
    
    def test_leverage_impact(self):
        """Testa calcolo impatto leva."""
        result = calculate_leverage_impact(
            position_value=10000,
            leverage=10,
            price_change_pct=5,
        )
        
        assert "error" not in result
        assert result["margin_required"] == 1000  # 10000/10
        assert result["pnl_dollars"] == 500  # 5% di 10000
        assert result["pnl_on_margin_pct"] == 50  # 500 su 1000 = 50%
        assert result["liquidation_approx_pct"] == 10  # 100/10
    
    def test_compound_growth(self):
        """Testa calcolo crescita composta."""
        result = calculate_compound_growth(
            initial=10000,
            monthly_return_pct=5,
            months=12,
            monthly_contribution=0,
        )
        
        assert "error" not in result
        assert result["final_value"] > 10000
        # (1.05)^12 ≈ 1.796, quindi ~17960
        assert result["final_value"] > 17000


class TestTradingQueryParsing:
    """Test parsing query trading."""
    
    def test_extract_prices(self):
        """Testa estrazione prezzi."""
        params = extract_trading_params("entry 100 sl 95 tp 115")
        
        assert "entry_price" in params
        assert "stop_loss" in params
        assert "take_profit" in params
    
    def test_extract_leverage(self):
        """Testa estrazione leva."""
        params = extract_trading_params("impatto leva 10x")
        
        assert "leverage" in params
        assert params["leverage"] == 10
    
    def test_is_trading_query(self):
        """Testa riconoscimento query trading."""
        assert is_trading_query("position size account 10000") == True
        assert is_trading_query("risk reward entry 100") == True
        assert is_trading_query("stop loss 95") == True
        assert is_trading_query("che tempo fa") == False


# ===================== EDGE CASES =====================

class TestEdgeCases:
    """Test per casi limite."""
    
    def test_ev_invalid_inputs(self):
        """Testa EV con input non validi."""
        result = calculate_ev(odds=0, probability=0.5, stake=100)
        assert "error" in result or result["ev"] == 0
        
        result = calculate_ev(odds=2.0, probability=1.5, stake=100)
        assert "error" in result or result["ev"] == 0
    
    def test_position_size_invalid(self):
        """Testa position size con input non validi."""
        result = calculate_position_size(
            account_size=-1000,
            risk_percent=2,
            entry_price=100,
            stop_loss_price=95,
        )
        assert "error" in result
    
    def test_rr_invalid_direction(self):
        """Testa R:R con SL/TP incompatibili."""
        # Long ma TP < Entry
        result = calculate_risk_reward(
            entry_price=100,
            stop_loss=95,
            take_profit=90,  # Invalido per long
        )
        assert "error" in result


# ===================== RUN TESTS =====================

if __name__ == "__main__":
    if not IMPORTS_OK:
        print("❌ Cannot run tests: imports failed")
        sys.exit(1)
    
    # Run with pytest
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
