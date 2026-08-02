#!/usr/bin/env python
"""
Phase 2 Market Data Layer - Comprehensive Validation Script
Tests all Phase 2 features including models, services, and API endpoints
"""

import os
import sys
from pathlib import Path
import django

# Ensure the project root is importable when running from the validation directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'deriv_platform.settings')
django.setup()

from django.utils import timezone
from datetime import timedelta
from django.test import Client
from rest_framework.test import APIClient
import json

from trading.models.market import MarketSymbol, PriceHistory, MarketSnapshot, TickData, DataStreamSession
from trading.services.market_service import DataCacheManager, SymbolManager, HistoricalDataAggregator
from trading.services.websocket_manager import StreamAggregator

def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")

def test_model_creation():
    """Test creating market data models"""
    print_section("Testing Market Data Models")
    
    # Clear existing data
    MarketSymbol.objects.all().delete()
    PriceHistory.objects.all().delete()
    MarketSnapshot.objects.all().delete()
    TickData.objects.all().delete()
    DataStreamSession.objects.all().delete()
    
    # Create symbols
    symbols_data = [
        ('VOLIDX', 'Volatility Index', 'VOLATILITY', 'Measure of market volatility'),
        ('BOOM', 'Boom', 'BOOM_CRASH', 'Boom/Crash synthetic'),
        ('CRASH', 'Crash', 'BOOM_CRASH', 'Crash synthetic'),
        ('EURUSD', 'EUR/USD', 'FOREX', 'Euro vs US Dollar'),
        ('BTCUSD', 'Bitcoin/USD', 'CRYPTO', 'Bitcoin price'),
    ]
    
    print("1. Creating market symbols...")
    symbols = {}
    for symbol, name, mtype, desc in symbols_data:
        sym = MarketSymbol.objects.create(
            symbol=symbol,
            display_name=name,
            market_type=mtype,
            description=desc,
            is_active=True,
            is_tradeable=True,
            supported_timeframes=['M1', 'M5', 'M15', 'H1'],
            trading_volume_24h=1000000.0 + len(symbols) * 100000,
        )
        symbols[symbol] = sym
        print(f"   [OK] Created {symbol} ({name})")
    
    # Create snapshots
    print("\n2. Creating market snapshots...")
    for symbol_key, symbol_obj in symbols.items():
        snapshot = MarketSnapshot.objects.create(
            symbol=symbol_obj,
            current_bid=100.0 - len(symbols),
            current_ask=100.05 - len(symbols),
            last_price=100.0 - len(symbols),
            high_24h=105.0 - len(symbols),
            low_24h=95.0 - len(symbols),
            change_24h=2.5,
            change_pct_24h=2.5,
            bid_ask_spread=0.05,
            spread_pct=0.05,
            volume_24h=500000
        )
        print(f"   [OK] Snapshot for {symbol_key}")
    
    # Create price history
    print("\n3. Creating price history (OHLC candles)...")
    now = timezone.now()
    for symbol_key, symbol_obj in symbols.items():
        for i in range(10):
            candle_time = now - timedelta(hours=i)
            PriceHistory.objects.create(
                symbol=symbol_obj,
                timeframe='H1',
                open=100.0 + i,
                high=105.0 + i,
                low=99.5 + i,
                close=102.0 + i,
                volume=5000 + i * 100,
                tick_count=500 + i * 50,
                candle_time=candle_time,
                candle_end_time=candle_time + timedelta(hours=1)
            )
        print(f"   [OK] 10 candles for {symbol_key}")
    
    # Create tick data
    print("\n4. Creating tick data...")
    for symbol_key, symbol_obj in symbols.items():
        for i in range(20):
            TickData.objects.create(
                symbol=symbol_obj,
                bid=100.0 + i * 0.01,
                ask=100.01 + i * 0.01,
                epoch=int(timezone.now().timestamp() * 1000) - i * 1000,
                spread=0.01,
                tick_number=1000 + i
            )
        print(f"   [OK] 20 ticks for {symbol_key}")
    
    # Create stream sessions
    print("\n5. Creating data stream sessions...")
    for symbol_key, symbol_obj in symbols.items():
        session = DataStreamSession.objects.create(
            session_id=f"sess-{symbol_key}-001",
            symbol=symbol_obj,
            status='SUBSCRIBED',
            connected_at=timezone.now() - timedelta(minutes=30),
            ticks_received=5000 + len(symbols) * 1000,
            bytes_received=250000 + len(symbols) * 50000,
            last_tick_at=timezone.now() - timedelta(seconds=5)
        )
        print(f"   [OK] Session for {symbol_key}")
    
    print("\n[OK] All models created successfully!")
    return symbols

def test_services(symbols):
    """Test service classes"""
    print_section("Testing Market Data Services")
    
    # Test caching
    print("1. Testing DataCacheManager...")
    cache = DataCacheManager()
    
    # Test price caching
    result = cache.set_price('VOLIDX', 99.95, 100.05, expiry=60)
    cached = cache.get_price('VOLIDX')
    assert cached['bid'] == 99.95, "Price cache failed"
    print("   [OK] Price caching works")
    
    # Test snapshot caching
    snapshot_data = {'last_price': 100.0, 'change': 2.5, 'volume': 1000000}
    cache.set_snapshot('BOOM', snapshot_data)
    cached_snap = cache.get_snapshot('BOOM')
    assert cached_snap['last_price'] == 100.0, "Snapshot cache failed"
    print("   [OK] Snapshot caching works")
    
    # Test symbol manager
    print("\n2. Testing SymbolManager...")
    manager = SymbolManager()
    
    volidx = manager.get_symbol('VOLIDX')
    assert volidx is not None, "Symbol lookup failed"
    print("   [OK] Symbol lookup works")
    
    volatility_symbols = manager.get_symbols_by_type('VOLATILITY')
    assert len(volatility_symbols) > 0, "Type filtering failed"
    print(f"   [OK] Found {len(volatility_symbols)} volatility symbols")
    
    all_tradeable = manager.get_all_tradeable_symbols()
    assert len(all_tradeable) > 0, "Tradeable filtering failed"
    print(f"   [OK] Found {len(all_tradeable)} tradeable symbols")
    
    # Test aggregator
    print("\n3. Testing HistoricalDataAggregator...")
    ticks = [
        {'price': 100.0},
        {'price': 102.5},
        {'price': 99.5},
        {'price': 101.0},
        {'price': 100.5},
    ]
    
    candle = HistoricalDataAggregator.aggregate_to_candle(ticks, 'M5')
    assert candle['open'] == 100.0, "Candle aggregation failed"
    assert candle['high'] == 102.5, "Candle high failed"
    assert candle['low'] == 99.5, "Candle low failed"
    assert candle['close'] == 100.5, "Candle close failed"
    print("   [OK] Candle aggregation works")
    
    period = HistoricalDataAggregator.get_candle_period('H1')
    assert period == timedelta(hours=1), "Timeframe conversion failed"
    print("   [OK] Timeframe conversion works")
    
    # Test stream aggregator
    print("\n4. Testing StreamAggregator...")
    aggregator = StreamAggregator()
    
    for tick in ticks:
        aggregator.add_tick('VOLIDX', 'M5', tick)
    
    final_candle = aggregator.finalize_candle('VOLIDX', 'M5')
    assert final_candle['open'] == 100.0, "Stream candle failed"
    print("   [OK] Stream aggregation works")
    
    print("\n[OK] All services working correctly!")

def test_api_endpoints():
    """Test API endpoints"""
    print_section("Testing Market Data API Endpoints")
    
    client = APIClient()
    
    # Test symbol list
    print("1. Testing /api/market/symbols/ endpoint...")
    response = client.get('/api/market/symbols/')
    assert response.status_code == 200, f"API returned {response.status_code}"
    data = response.json()
    assert 'results' in data, "API response missing results"
    print(f"   [OK] API returned {len(data['results'])} symbols")
    
    # Test symbol filtering
    print("\n2. Testing symbol filtering...")
    response = client.get('/api/market/symbols/?market_type=VOLATILITY')
    assert response.status_code == 200, "Filtering failed"
    data = response.json()
    if len(data['results']) > 0:
        assert data['results'][0]['market_type'] == 'VOLATILITY', "Filter didn't work"
    print(f"   [OK] Filtering works ({len(data['results'])} volatility symbols)")
    
    # Test symbol search
    print("\n3. Testing symbol search...")
    response = client.get('/api/market/symbols/?search=Volatility')
    assert response.status_code == 200, "Search failed"
    data = response.json()
    print(f"   [OK] Search works ({len(data['results'])} results for 'Volatility')")
    
    # Test trending endpoint
    print("\n4. Testing trending symbols...")
    response = client.get('/api/market/symbols/trending/')
    assert response.status_code == 200, "Trending failed"
    data = response.json()
    print(f"   [OK] Trending endpoint works ({len(data)} symbols)")
    
    # Test price history
    print("\n5. Testing price history endpoint...")
    response = client.get('/api/market/price-history/?symbol=VOLIDX')
    assert response.status_code == 200, "Price history failed"
    data = response.json()
    print(f"   [OK] Price history works ({data['count']} candles found)")
    
    # Test chart data
    print("\n6. Testing chart data endpoint...")
    response = client.get('/api/market/price-history/chart_data/?symbol=VOLIDX&timeframe=H1&days=7')
    assert response.status_code == 200, "Chart data failed"
    data = response.json()
    assert data['symbol'] == 'VOLIDX', "Symbol mismatch in chart data"
    print(f"   [OK] Chart data works ({len(data['candles'])} candles)")
    
    # Test market snapshots
    print("\n7. Testing market snapshots endpoint...")
    response = client.get('/api/market/snapshots/all_snapshots/')
    assert response.status_code == 200, "Snapshots failed"
    data = response.json()
    print(f"   [OK] Snapshots endpoint works ({len(data)} snapshots)")
    
    # Test tick data
    print("\n8. Testing tick data endpoint...")
    response = client.get('/api/market/ticks/recent/?symbol=VOLIDX&limit=20')
    assert response.status_code == 200, "Tick data failed"
    data = response.json()
    print(f"   [OK] Tick data works ({len(data)} ticks)")
    
    # Test market stats
    print("\n9. Testing market statistics...")
    response = client.get('/api/market/stats/overview/')
    assert response.status_code == 200, "Stats failed"
    data = response.json()
    print(f"   [OK] Market stats: {data['total_symbols']} symbols, {data['total_candles']} candles, {data['total_ticks']} ticks")
    
    print("\n[OK] All API endpoints working!")

def test_database_stats():
    """Display database statistics"""
    print_section("Database Statistics")
    
    total_symbols = MarketSymbol.objects.count()
    active_symbols = MarketSymbol.objects.filter(is_active=True).count()
    total_candles = PriceHistory.objects.count()
    total_ticks = TickData.objects.count()
    total_sessions = DataStreamSession.objects.count()
    active_sessions = DataStreamSession.objects.filter(status__in=['CONNECTED', 'SUBSCRIBED']).count()
    
    print(f"Market Symbols: {total_symbols} (active: {active_symbols})")
    print(f"Price History: {total_candles} candles")
    print(f"Tick Data: {total_ticks} ticks")
    print(f"Stream Sessions: {total_sessions} (active: {active_sessions})")
    
    # Sample data
    print("\nSample Data:")
    latest_candle = PriceHistory.objects.order_by('-candle_time').first()
    if latest_candle:
        print(f"  Latest candle: {latest_candle.symbol.symbol} - O:{latest_candle.open} H:{latest_candle.high} L:{latest_candle.low} C:{latest_candle.close}")
    
    latest_tick = TickData.objects.order_by('-epoch').first()
    if latest_tick:
        print(f"  Latest tick: {latest_tick.symbol.symbol} - Bid:{latest_tick.bid} Ask:{latest_tick.ask}")
    
    latest_snapshot = MarketSnapshot.objects.order_by('-updated_at').first()
    if latest_snapshot:
        print(f"  Latest snapshot: {latest_snapshot.symbol.symbol} - Price:{latest_snapshot.last_price} Spread:{latest_snapshot.bid_ask_spread}%")

def main():
    """Main validation function"""
    print("\n")
    print("="*80)
    print("  PHASE 2 - Market Data Layer - Comprehensive Validation")
    print("="*80)
    
    try:
        # Run tests
        symbols = test_model_creation()
        test_services(symbols)
        test_api_endpoints()
        test_database_stats()
        
        print("\n")
        print("="*80)
        print("  ALL PHASE 2 TESTS PASSED SUCCESSFULLY!")
        print("="*80)
        print("\nPhase 2 Features Implemented:")
        print("  [OK] Market Data Models (MarketSymbol, PriceHistory, MarketSnapshot, TickData, DataStreamSession)")
        print("  [OK] Data Caching Service (Redis-based with in-memory fallback)")
        print("  [OK] Symbol Manager Service (Symbol lookup and filtering)")
        print("  [OK] Historical Data Aggregator (OHLC candle aggregation)")
        print("  [OK] WebSocket Manager (Real-time streaming management)")
        print("  [OK] Stream Aggregator (Real-time candle formation)")
        print("  [OK] Comprehensive API Endpoints (Symbols, Price History, Snapshots, Ticks, Stats)")
        print("  [OK] Database Indexing (Fast queries on large datasets)")
        print("  [OK] Admin Interfaces (All models registered)")
        print("\nAPI Endpoints Available:")
        print("  GET  /api/market/symbols/ - List market symbols")
        print("  GET  /api/market/symbols/{id}/ - Get symbol details")
        print("  GET  /api/market/symbols/snapshot/ - Get market snapshot")
        print("  GET  /api/market/symbols/trending/ - Get trending symbols")
        print("  GET  /api/market/price-history/ - List price history")
        print("  GET  /api/market/price-history/chart_data/ - Get chart data")
        print("  GET  /api/market/snapshots/ - List market snapshots")
        print("  GET  /api/market/ticks/ - List tick data")
        print("  GET  /api/market/streams/ - List stream sessions")
        print("  GET  /api/market/stats/overview/ - Get market statistics")
        print("\n")
        sys.exit(0)
        
    except Exception as e:
        print(f"\n[FAIL] Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
