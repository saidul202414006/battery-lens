import sys
import os

# Add project root to path so we can import modules
sys.path.insert(0, os.path.abspath('.'))

from platform_adapters.windows_adapter import WindowsAdapter

def main():
    print("Testing Windows Adapter...")
    adapter = WindowsAdapter()
    
    print("\n--- Battery Snapshot ---")
    snapshot = adapter.get_battery_snapshot()
    print(f"Timestamp: {snapshot.timestamp}")
    print(f"Percent: {snapshot.percent}%")
    print(f"Plugged In: {snapshot.power_plugged}")
    print(f"Design Capacity: {snapshot.design_capacity_mwh}")
    print(f"Full Capacity: {snapshot.full_charge_capacity_mwh}")
    
    print("\n--- Top Processes ---")
    processes = adapter.get_top_processes_by_cpu(limit=3)
    for p in processes:
        print(f"Process: {p.process_name:<20} CPU: {p.cpu_percent:5.1f}%  MEM: {p.memory_mb:6.1f}MB")
        
    print("\n--- Sleep Events (last 24h) ---")
    import time
    yesterday = int(time.time()) - (24 * 3600)
    events = adapter.get_sleep_events_since(yesterday)
    print(f"Found {len(events)} sleep events.")
    for e in events:
        print(f"Sleep at: {e.sleep_timestamp}")
        
    print("\nVerification Complete.")

if __name__ == "__main__":
    main()
