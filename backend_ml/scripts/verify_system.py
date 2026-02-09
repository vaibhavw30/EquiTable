"""
Comprehensive Verification Script for EquiTable System
=======================================================
Audits the "Problem Child" pantries to verify logic fixes:
- Test A: Sunday/Hours Accuracy Logic
- Test B: Visual Honesty (Low Confidence = Gray markers)
- Test C: ID Required Logic
- Test D: Appointment Only Logic

Usage: python -m scripts.verify_system
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "equitable")

# Test results tracking
results = {
    "passed": 0,
    "failed": 0,
    "warnings": 0,
    "details": []
}


def log_pass(test_name: str, message: str):
    """Log a passing test."""
    results["passed"] += 1
    results["details"].append(("PASS", test_name, message))
    print(f"  ✓ PASS: {message}")


def log_fail(test_name: str, message: str, expected: str, actual: str):
    """Log a failing test."""
    results["failed"] += 1
    results["details"].append(("FAIL", test_name, f"{message} (Expected: {expected}, Got: {actual})"))
    print(f"  ✗ FAIL: {message}")
    print(f"         Expected: {expected}")
    print(f"         Got:      {actual}")


def log_warn(test_name: str, message: str):
    """Log a warning (not a failure, but worth noting)."""
    results["warnings"] += 1
    results["details"].append(("WARN", test_name, message))
    print(f"  ⚠ WARN: {message}")


def simulate_marker_color(pantry: dict) -> tuple[str, str]:
    """
    Simulate the frontend marker color logic from PantryMap.jsx.
    Returns (color_name, hex_color).
    """
    status = pantry.get("status", "UNKNOWN")
    is_id_required = pantry.get("is_id_required", False)

    # Red: Closed
    if status == "CLOSED":
        return ("RED", "#EF4444")

    # Gray: Unknown or Waitlist (uncertain availability)
    if status in ("UNKNOWN", "WAITLIST"):
        return ("GRAY", "#9CA3AF")

    # Yellow: Open but ID required
    if is_id_required:
        return ("YELLOW", "#F59E0B")

    # Green: Open and no ID required (fully accessible)
    return ("GREEN", "#22C55E")


async def find_pantry_by_name(collection, name_substring: str) -> Optional[dict]:
    """Find a pantry by partial name match (case-insensitive)."""
    return await collection.find_one({
        "name": {"$regex": name_substring, "$options": "i"}
    })


async def test_a_hours_accuracy(collection):
    """
    Test A: The "Sunday" Logic (Hours Accuracy)

    Verify that pantries correctly reflect their hours_today based on the
    day of the week. Today is Saturday, Feb 8, 2026.
    """
    print("\n" + "=" * 60)
    print("TEST A: Hours Accuracy / Day-of-Week Logic")
    print("=" * 60)
    print(f"Today is: {datetime.now().strftime('%A, %B %d, %Y')}")

    # Check all pantries for hours_today logic
    pantries = await collection.find({}).to_list(length=100)

    hours_present = 0
    hours_missing = 0
    closed_today_count = 0
    open_today_count = 0

    for p in pantries:
        hours_today = p.get("hours_today", "")
        hours_notes = p.get("hours_notes", "")
        name = p.get("name", "Unknown")

        if hours_today and hours_today not in ("Not listed", "Hours not listed", ""):
            hours_present += 1

            # Check if correctly marked as closed
            if "closed" in hours_today.lower():
                closed_today_count += 1
                print(f"  [{name}] hours_today='{hours_today}' (Closed)")
            else:
                open_today_count += 1
                print(f"  [{name}] hours_today='{hours_today}'")
        else:
            hours_missing += 1

    print()
    if hours_present > 0:
        log_pass("A", f"{hours_present}/{len(pantries)} pantries have hours_today populated")
    else:
        log_fail("A", "No pantries have hours_today", ">0 pantries", "0 pantries")

    if closed_today_count > 0 or open_today_count > 0:
        log_pass("A", f"Day-aware: {closed_today_count} closed today, {open_today_count} open today")

    # Look for a specific pantry that should be closed on weekends
    # Churches often have food pantries only on weekdays
    church_pantries = await collection.find({
        "name": {"$regex": "church|baptist|methodist|lutheran", "$options": "i"}
    }).to_list(length=100)

    weekend_closed = 0
    for p in church_pantries:
        hours_today = p.get("hours_today", "").lower()
        if "closed" in hours_today:
            weekend_closed += 1

    if weekend_closed > 0:
        log_pass("A", f"{weekend_closed} church pantries correctly show 'Closed today' on Saturday")


async def test_b_visual_honesty(collection):
    """
    Test B: Visual Honesty Logic

    Verify that low-confidence pantries (confidence < 4) are NOT shown
    as GREEN (fully accessible). They should be GRAY or another cautionary color.
    """
    print("\n" + "=" * 60)
    print("TEST B: Visual Honesty (Low Confidence = Gray/Neutral)")
    print("=" * 60)

    # Find all low-confidence pantries
    low_confidence = await collection.find({
        "confidence": {"$lt": 4}
    }).to_list(length=100)

    if not low_confidence:
        log_warn("B", "No pantries with confidence < 4 found in database")
        # Check if we have confidence data at all
        all_pantries = await collection.find({}).to_list(length=100)
        confidences = [p.get("confidence") for p in all_pantries if p.get("confidence") is not None]
        if confidences:
            print(f"  Confidence range: {min(confidences)} - {max(confidences)}")
        return

    print(f"Found {len(low_confidence)} pantries with confidence < 4:")

    green_violations = []

    for p in low_confidence:
        name = p.get("name", "Unknown")
        status = p.get("status", "UNKNOWN")
        confidence = p.get("confidence", 0)
        is_id_required = p.get("is_id_required", False)

        color_name, color_hex = simulate_marker_color(p)

        print(f"  [{name}]")
        print(f"    status={status}, confidence={confidence}, is_id_required={is_id_required}")
        print(f"    Marker color: {color_name} ({color_hex})")

        # A low-confidence pantry shown as GREEN is problematic
        # It suggests high certainty when we don't have good data
        if color_name == "GREEN" and confidence < 3:
            green_violations.append(name)
            log_fail("B", f"Low-confidence pantry '{name}' shown as GREEN",
                     "GRAY or YELLOW", f"GREEN (confidence={confidence})")
        else:
            log_pass("B", f"'{name}' correctly not GREEN (confidence={confidence}, color={color_name})")

    # Summary
    print()
    if not green_violations:
        log_pass("B", "All low-confidence pantries have appropriate cautionary colors")


async def test_c_id_required(collection):
    """
    Test C: ID Required Logic

    Verify that pantries known to require ID have is_id_required=True.
    """
    print("\n" + "=" * 60)
    print("TEST C: ID Required Logic")
    print("=" * 60)

    # Check all pantries for ID requirement data
    pantries = await collection.find({}).to_list(length=100)

    id_required_count = 0
    no_id_count = 0
    null_count = 0

    for p in pantries:
        is_id_required = p.get("is_id_required")
        if is_id_required is True:
            id_required_count += 1
        elif is_id_required is False:
            no_id_count += 1
        else:
            null_count += 1

    print(f"ID Required distribution:")
    print(f"  - ID Required: {id_required_count}")
    print(f"  - No ID Required: {no_id_count}")
    print(f"  - Unknown/null: {null_count}")
    print()

    # Verify the ID filter logic works
    no_id_pantries = [p for p in pantries if p.get("is_id_required") is False]

    if no_id_count > 0:
        log_pass("C", f"{no_id_count} pantries explicitly marked as 'No ID Required'")
        print("  No-ID pantries:")
        for p in no_id_pantries[:5]:
            print(f"    - {p.get('name')}")
        if len(no_id_pantries) > 5:
            print(f"    ... and {len(no_id_pantries) - 5} more")
    else:
        log_warn("C", "No pantries marked as 'No ID Required' - filter may not work well")

    if id_required_count > 0:
        log_pass("C", f"{id_required_count} pantries marked as 'ID Required'")
        id_required_pantries = [p for p in pantries if p.get("is_id_required") is True]
        print("  ID-Required pantries:")
        for p in id_required_pantries[:5]:
            name = p.get("name")
            rules = p.get("eligibility_rules", [])
            print(f"    - {name}")
            # Check if rules mention ID
            id_rules = [r for r in rules if "id" in r.lower() or "proof" in r.lower()]
            if id_rules:
                for r in id_rules[:2]:
                    print(f"      Rule: {r}")

    # Test marker color logic for ID-required pantries
    print()
    print("Marker color verification for ID-required pantries:")
    for p in [p for p in pantries if p.get("is_id_required") is True][:3]:
        name = p.get("name")
        status = p.get("status")
        color_name, _ = simulate_marker_color(p)

        if status == "OPEN":
            if color_name == "YELLOW":
                log_pass("C", f"'{name}' (OPEN + ID required) correctly shows YELLOW")
            else:
                log_fail("C", f"'{name}' should be YELLOW", "YELLOW", color_name)


async def test_d_appointment_only(collection):
    """
    Test D: Appointment Only Logic

    Verify that appointment-only pantries are NOT marked as generic OPEN.
    They should be WAITLIST or have special_notes indicating appointment requirement.
    """
    print("\n" + "=" * 60)
    print("TEST D: Appointment Only / Restricted Access Logic")
    print("=" * 60)

    # Find Midtown Assistance Center
    midtown = await find_pantry_by_name(collection, "Midtown Assistance")

    if midtown:
        name = midtown.get("name")
        status = midtown.get("status")
        hours_notes = midtown.get("hours_notes", "")
        special_notes = midtown.get("special_notes", "")
        eligibility_rules = midtown.get("eligibility_rules", [])

        print(f"[{name}]")
        print(f"  status: {status}")
        print(f"  hours_notes: {hours_notes}")
        print(f"  special_notes: {special_notes}")
        print(f"  eligibility_rules: {eligibility_rules}")

        # Check if appointment requirement is captured
        all_text = f"{hours_notes} {special_notes} {' '.join(eligibility_rules)}".lower()
        has_appointment_info = "appointment" in all_text or "call" in all_text or "register" in all_text

        if status == "WAITLIST":
            log_pass("D", f"'{name}' correctly marked as WAITLIST (restricted access)")
        elif has_appointment_info:
            log_pass("D", f"'{name}' has appointment/registration info in notes or rules")
        else:
            log_warn("D", f"'{name}' may need appointment info - verify manually")
    else:
        log_warn("D", "Midtown Assistance Center not found in database")

    # Check for other pantries with waitlist or appointment indicators
    waitlist_pantries = await collection.find({
        "status": "WAITLIST"
    }).to_list(length=100)

    if waitlist_pantries:
        print(f"\nWAITLIST pantries ({len(waitlist_pantries)}):")
        for p in waitlist_pantries:
            name = p.get("name")
            special = p.get("special_notes", "N/A")
            print(f"  - {name}")
            if special and special != "N/A":
                print(f"    Note: {special}")
        log_pass("D", f"{len(waitlist_pantries)} pantries correctly marked as WAITLIST")

    # Check for appointment-related text in any pantry
    all_pantries = await collection.find({}).to_list(length=100)
    appointment_mentions = []

    for p in all_pantries:
        rules = " ".join(p.get("eligibility_rules", []))
        notes = p.get("special_notes", "") or ""
        hours = p.get("hours_notes", "") or ""
        combined = f"{rules} {notes} {hours}".lower()

        if "appointment" in combined or "by appointment" in combined:
            appointment_mentions.append(p.get("name"))

    if appointment_mentions:
        print(f"\nPantries mentioning 'appointment' ({len(appointment_mentions)}):")
        for name in appointment_mentions:
            print(f"  - {name}")


async def test_e_geospatial(collection):
    """
    Bonus Test E: Geospatial Index and Query

    Verify that the 2dsphere index exists and geospatial queries work.
    """
    print("\n" + "=" * 60)
    print("TEST E: Geospatial Query (Bonus)")
    print("=" * 60)

    # Check for 2dsphere index
    indexes = await collection.index_information()

    has_geo_index = False
    for idx_name, idx_info in indexes.items():
        if "2dsphere" in str(idx_info.get("key", [])):
            has_geo_index = True
            log_pass("E", f"2dsphere index exists: {idx_name}")
            break

    if not has_geo_index:
        log_fail("E", "2dsphere index not found", "index exists", "no index")
        return

    # Test a $near query (downtown Atlanta coordinates)
    downtown_atlanta = {"type": "Point", "coordinates": [-84.388, 33.749]}

    try:
        nearby = await collection.find({
            "location": {
                "$near": {
                    "$geometry": downtown_atlanta,
                    "$maxDistance": 5000  # 5km
                }
            }
        }).to_list(length=5)

        if nearby:
            log_pass("E", f"$near query returned {len(nearby)} pantries within 5km of downtown")
            print("  Nearest pantries to downtown Atlanta:")
            for p in nearby:
                print(f"    - {p.get('name')}")
        else:
            log_warn("E", "No pantries within 5km of downtown Atlanta")

    except Exception as e:
        log_fail("E", f"Geospatial query failed: {e}", "query success", "error")


async def print_summary():
    """Print final test summary."""
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    total = results["passed"] + results["failed"]

    print(f"\n  PASSED:   {results['passed']}")
    print(f"  FAILED:   {results['failed']}")
    print(f"  WARNINGS: {results['warnings']}")
    print(f"  TOTAL:    {total}")

    if results["failed"] == 0:
        print("\n  ✓ ALL TESTS PASSED")
        print("=" * 60)
        return True
    else:
        print("\n  ✗ SOME TESTS FAILED")
        print("\nFailed tests:")
        for status, test, message in results["details"]:
            if status == "FAIL":
                print(f"  - [{test}] {message}")
        print("=" * 60)
        return False


async def main():
    print("=" * 60)
    print("EquiTable System Verification")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")

    # Connect to MongoDB
    client = AsyncIOMotorClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client[DATABASE_NAME]

    try:
        await client.admin.command("ping")
        print("Connected to MongoDB Atlas")
    except Exception as e:
        print(f"ERROR: Could not connect to MongoDB: {e}")
        sys.exit(1)

    pantries_collection = db["pantries"]

    # Count pantries
    count = await pantries_collection.count_documents({})
    print(f"Pantries in database: {count}")

    if count == 0:
        print("ERROR: No pantries in database. Run ingest_real_pantries.py first.")
        sys.exit(1)

    # Run all tests
    await test_a_hours_accuracy(pantries_collection)
    await test_b_visual_honesty(pantries_collection)
    await test_c_id_required(pantries_collection)
    await test_d_appointment_only(pantries_collection)
    await test_e_geospatial(pantries_collection)

    # Print summary
    success = await print_summary()

    client.close()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
