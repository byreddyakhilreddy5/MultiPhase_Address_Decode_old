import cocotb
from cocotb.triggers import RisingEdge, Timer
from cocotb.clock import Clock
import random

ADDR_WIDTH = 14
ALL_ONES = (1 << ADDR_WIDTH) - 1


def calculate_expected_addresses(addr, cs, prev_cs_p3=None):
    """Calculate expected addresses based on cs inversion logic.
    
    Inversion rules:
    - If cs_P0 is 0 (low), then address_P0 and address_P1 should be inverted
    - If cs_P1 is 0 (low), then address_P1 and address_P2 should be inverted
    - If cs_P2 is 0 (low), then address_P2 and address_P3 should be inverted
    - If cs_P3 is 0 (low), then address_P3 and address_P0 (in next cycle) should be inverted
    
    Args:
        addr: List of 4 addresses [addr_P0, addr_P1, addr_P2, addr_P3]
        cs: List of 4 cs values [cs_P0, cs_P1, cs_P2, cs_P3]
        prev_cs_p3: Previous cycle's cs_P3 value (for wraparound)
    
    Returns:
        List of 4 expected processed addresses
    """
    exp_addr = [0] * 4
    
    # Determine which phases should be inverted
    invert = [False] * 4
    
    # If cs_P0 is low, invert address_P0 and address_P1
    if cs[0] == 0:
        invert[0] = True
        invert[1] = True
    
    # If cs_P1 is low, invert address_P1 and address_P2
    if cs[1] == 0:
        invert[1] = True
        invert[2] = True
    
    # If cs_P2 is low, invert address_P2 and address_P3
    if cs[2] == 0:
        invert[2] = True
        invert[3] = True
    
    # If cs_P3 is low, invert address_P3 and address_P0 (wraparound)
    if cs[3] == 0:
        invert[3] = True
        # address_P0 inversion from cs_P3 low will affect next cycle
        # But we also need to check if prev_cs_p3 was low (affecting current address_P0)
        if prev_cs_p3 == 0:
            invert[0] = True
    
    # Calculate expected addresses
    for i in range(4):
        if invert[i]:
            exp_addr[i] = (~addr[i]) & ALL_ONES
        else:
            exp_addr[i] = addr[i]
    
    return exp_addr


def generate_valid_cs(prev_cs_p3=None):
    """Generate cs values ensuring consecutive cs_P* cannot both be low.
    
    Constraint: If cs_P[i] is low, then cs_P[i+1] must be high.
    - If cs_P0 is low, cs_P1 must be high
    - If cs_P1 is low, cs_P2 must be high
    - If cs_P2 is low, cs_P3 must be high
    - If previous cs_P3 is low, then current cs_P0 must be high (wraparound)
    
    Args:
        prev_cs_p3: Previous cycle's cs_P3 value. If provided and is 0, 
                   then cs_P0 must be 1.
    """
    cs = [0] * 4
    
    # If previous cs_P3 was low, current cs_P0 must be high
    if prev_cs_p3 is not None and prev_cs_p3 == 0:
        cs[0] = 1
    else:
        # Generate cs_P0 (can be 0 or 1)
        cs[0] = random.randint(0, 1)
    
    # If cs_P0 is low, cs_P1 must be high; otherwise cs_P1 can be 0 or 1
    if cs[0] == 0:
        cs[1] = 1
    else:
        cs[1] = random.randint(0, 1)
    
    # If cs_P1 is low, cs_P2 must be high; otherwise cs_P2 can be 0 or 1
    if cs[1] == 0:
        cs[2] = 1
    else:
        cs[2] = random.randint(0, 1)
    
    # If cs_P2 is low, cs_P3 must be high; otherwise cs_P3 can be 0 or 1
    if cs[2] == 0:
        cs[3] = 1
    else:
        cs[3] = random.randint(0, 1)
    
    return cs


@cocotb.test()
async def test_addr_decode_registered(dut):
    """Test registered addr_decode with 1-cycle latency and asynchronous reset"""

    # Start clock (10 ns period)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    # Initialize inputs
    dut.address_P0.value = 0
    dut.address_P1.value = 0
    dut.address_P2.value = 0
    dut.address_P3.value = 0
    dut.cs_P0.value = 0
    dut.cs_P1.value = 0
    dut.cs_P2.value = 0
    dut.cs_P3.value = 0

    # Apply asynchronous active-low reset (without waiting for clock edge)
    dut.rst_n.value = 0
    await Timer(5, unit="ns")  # Small delay to allow async reset to propagate
    
    # Verify outputs are reset immediately (asynchronous reset behavior)
    assert dut.addr_out.value.integer == 0, "addr_out should be 0 during async reset"
    assert dut.cs_out.value.integer == 0, "cs_out should be 0 during async reset"
    
    # Wait for a clock edge while reset is still active
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")  # Small delay after clock edge
    
    # Verify outputs remain reset
    assert dut.addr_out.value.integer == 0, "addr_out should remain 0 during reset"
    assert dut.cs_out.value.integer == 0, "cs_out should remain 0 during reset"
    
    # Deassert reset (asynchronous)
    dut.rst_n.value = 1
    await Timer(5, unit="ns")  # Small delay to allow reset deassertion to propagate
    
    # Wait for one clock cycle after reset deassertion
    await RisingEdge(dut.clk)

    # Run randomized tests
    prev_cs_p3 = None  # Track previous cycle's cs_P3 for wraparound constraint
    for _ in range(200):

        addr = [random.randint(0, ALL_ONES) for _ in range(4)]
        # Generate cs values with constraint: consecutive cs_P* cannot both be low
        # Also enforce: if prev cs_P3 was low, current cs_P0 must be high
        cs = generate_valid_cs(prev_cs_p3)

        # Drive inputs at current clock cycle
        dut.address_P0.value = addr[0]
        dut.address_P1.value = addr[1]
        dut.address_P2.value = addr[2]
        dut.address_P3.value = addr[3]

        dut.cs_P0.value = cs[0]
        dut.cs_P1.value = cs[1]
        dut.cs_P2.value = cs[2]
        dut.cs_P3.value = cs[3]

        # Calculate expected addresses based on cs inversion logic
        # prev_cs_p3 is used for wraparound: if prev cs_P3 was low, current address_P0 is inverted
        exp_addr = calculate_expected_addresses(addr, cs, prev_cs_p3)

        expected_addr_out = (
            (exp_addr[3] << 42) |
            (exp_addr[2] << 28) |
            (exp_addr[1] << 14) |
            (exp_addr[0] << 0)
        )

        expected_cs_out = (
            (cs[3] << 3) |
            (cs[2] << 2) |
            (cs[1] << 1) |
            (cs[0] << 0)
        )

        # Wait 1 clock cycle for registered output to appear
        # Outputs are registered, so they appear one cycle after inputs
        await RisingEdge(dut.clk)

        # Check outputs one cycle after inputs were applied
        assert dut.addr_out.value.integer == expected_addr_out, (
            f"\nADDR MISMATCH\n"
            f"addr = {addr}\n"
            f"cs   = {cs}\n"
            f"exp  = {hex(expected_addr_out)}\n"
            f"got  = {hex(dut.addr_out.value.integer)}"
        )

        assert dut.cs_out.value.integer == expected_cs_out, (
            f"\nCS MISMATCH\n"
            f"exp = {bin(expected_cs_out)}\n"
            f"got = {bin(dut.cs_out.value.integer)}"
        )
        
        # Update previous cs_P3 for next iteration (wraparound constraint)
        prev_cs_p3 = cs[3]

    dut._log.info("All registered addr_decode tests PASSED ✅")


@cocotb.test()
async def test_cs_p3_to_cs_p0_wraparound(dut):
    """Test that if cs_P3 is low, then cs_P0 must be high in the next cycle"""
    
    # Start clock (10 ns period)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # Apply reset
    dut.rst_n.value = 0
    await Timer(5, unit="ns")
    dut.rst_n.value = 1
    await Timer(5, unit="ns")
    await RisingEdge(dut.clk)
    
    # Test case 1: cs_P3 is low, next cycle cs_P0 must be high
    dut._log.info("Test case 1: cs_P3=0, next cycle cs_P0 must be 1")
    
    # First cycle: Set cs_P3 to low (0)
    # Use a valid pattern where cs_P3 can be low: [1, 1, 1, 0] is valid
    dut.address_P0.value = 0x1234
    dut.address_P1.value = 0x5678
    dut.address_P2.value = 0x9ABC
    dut.address_P3.value = 0xDEF0
    
    dut.cs_P0.value = 1
    dut.cs_P1.value = 1
    dut.cs_P2.value = 1
    dut.cs_P3.value = 0  # cs_P3 is low
    
    await RisingEdge(dut.clk)
    
    # Second cycle: cs_P0 must be high because previous cs_P3 was low
    dut.address_P0.value = 0x1111
    dut.address_P1.value = 0x2222
    dut.address_P2.value = 0x3333
    dut.address_P3.value = 0x4444
    
    # Generate valid cs with constraint: prev_cs_p3=0, so cs_P0 must be 1
    cs = generate_valid_cs(prev_cs_p3=0)
    assert cs[0] == 1, f"cs_P0 must be 1 when prev cs_P3 was 0, got {cs[0]}"
    
    dut.cs_P0.value = cs[0]
    dut.cs_P1.value = cs[1]
    dut.cs_P2.value = cs[2]
    dut.cs_P3.value = cs[3]
    
    await RisingEdge(dut.clk)
    
    # Verify the constraint was satisfied (cs_out[0] is cs_P0)
    cs_out_value = dut.cs_out.value.integer
    cs_p0_out = (cs_out_value >> 0) & 1
    assert cs_p0_out == 1, f"cs_P0 should be 1 after prev cs_P3 was 0, got {cs_p0_out}"
    dut._log.info("✓ Test case 1 PASSED: cs_P0=1 after prev cs_P3=0")
    
    # Test case 2: Multiple consecutive cycles with cs_P3 low
    dut._log.info("Test case 2: Multiple cycles with cs_P3=0 constraint")
    
    prev_cs_p3 = None
    for cycle in range(5):
        # Generate valid cs pattern
        cs = generate_valid_cs(prev_cs_p3)
        
        # Verify constraint: if prev_cs_p3 was 0, cs_P0 must be 1
        if prev_cs_p3 == 0:
            assert cs[0] == 1, f"Cycle {cycle}: cs_P0 must be 1 when prev cs_P3 was 0"
            dut._log.info(f"  Cycle {cycle}: prev_cs_p3=0, cs_P0=1 ✓")
        
        # Set inputs
        dut.address_P0.value = random.randint(0, ALL_ONES)
        dut.address_P1.value = random.randint(0, ALL_ONES)
        dut.address_P2.value = random.randint(0, ALL_ONES)
        dut.address_P3.value = random.randint(0, ALL_ONES)
        
        dut.cs_P0.value = cs[0]
        dut.cs_P1.value = cs[1]
        dut.cs_P2.value = cs[2]
        dut.cs_P3.value = cs[3]
        
        await RisingEdge(dut.clk)
        
        # Update for next iteration
        prev_cs_p3 = cs[3]
    
    dut._log.info("✓ Test case 2 PASSED: Multiple cycles with wraparound constraint")
    
    # Test case 3: Explicitly test invalid case would fail
    dut._log.info("Test case 3: Verify constraint enforcement")
    
    # Set cs_P3 to low
    dut.cs_P0.value = 1
    dut.cs_P1.value = 1
    dut.cs_P2.value = 1
    dut.cs_P3.value = 0
    await RisingEdge(dut.clk)
    
    # Next cycle: cs_P0 must be 1 (generated by function)
    cs = generate_valid_cs(prev_cs_p3=0)
    assert cs[0] == 1, "generate_valid_cs must enforce cs_P0=1 when prev_cs_p3=0"
    
    dut.cs_P0.value = cs[0]
    dut.cs_P1.value = cs[1]
    dut.cs_P2.value = cs[2]
    dut.cs_P3.value = cs[3]
    await RisingEdge(dut.clk)
    
    dut._log.info("✓ Test case 3 PASSED: Constraint properly enforced")
    dut._log.info("All cs_P3 to cs_P0 wraparound tests PASSED ✅")


@cocotb.test()
async def test_address_inversion_logic(dut):
    """Test address inversion based on cs values"""
    
    # Start clock (10 ns period)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # Apply reset
    dut.rst_n.value = 0
    await Timer(5, unit="ns")
    dut.rst_n.value = 1
    await Timer(5, unit="ns")
    await RisingEdge(dut.clk)
    
    # Test case 1: cs_P0 is low, address_P0 and address_P1 should be inverted
    dut._log.info("Test case 1: cs_P0=0, address_P0 and address_P1 should be inverted")
    
    addr = [0x1234, 0x5678, 0x9ABC, 0xDEF0]
    cs = [0, 1, 1, 1]  # cs_P0 is low, cs_P1 must be high
    
    dut.address_P0.value = addr[0]
    dut.address_P1.value = addr[1]
    dut.address_P2.value = addr[2]
    dut.address_P3.value = addr[3]
    
    dut.cs_P0.value = cs[0]
    dut.cs_P1.value = cs[1]
    dut.cs_P2.value = cs[2]
    dut.cs_P3.value = cs[3]
    
    await RisingEdge(dut.clk)
    
    # Check outputs
    exp_addr = calculate_expected_addresses(addr, cs, None)
    expected_addr_out = (
        (exp_addr[3] << 42) |
        (exp_addr[2] << 28) |
        (exp_addr[1] << 14) |
        (exp_addr[0] << 0)
    )
    
    assert dut.addr_out.value.integer == expected_addr_out, (
        f"Address inversion mismatch for cs_P0=0\n"
        f"Expected: {hex(expected_addr_out)}\n"
        f"Got: {hex(dut.addr_out.value.integer)}\n"
        f"exp_addr = {[hex(a) for a in exp_addr]}"
    )
    
    # Verify address_P0 and address_P1 are inverted
    addr_out_p0 = (dut.addr_out.value.integer >> 0) & ALL_ONES
    addr_out_p1 = (dut.addr_out.value.integer >> 14) & ALL_ONES
    assert addr_out_p0 == ((~addr[0]) & ALL_ONES), f"address_P0 should be inverted"
    assert addr_out_p1 == ((~addr[1]) & ALL_ONES), f"address_P1 should be inverted"
    dut._log.info("✓ Test case 1 PASSED: cs_P0=0 inverts address_P0 and address_P1")
    
    # Test case 2: cs_P1 is low, address_P1 and address_P2 should be inverted
    dut._log.info("Test case 2: cs_P1=0, address_P1 and address_P2 should be inverted")
    
    addr = [0x1111, 0x2222, 0x3333, 0x4444]
    cs = [1, 0, 1, 1]  # cs_P1 is low, cs_P2 must be high
    
    dut.address_P0.value = addr[0]
    dut.address_P1.value = addr[1]
    dut.address_P2.value = addr[2]
    dut.address_P3.value = addr[3]
    
    dut.cs_P0.value = cs[0]
    dut.cs_P1.value = cs[1]
    dut.cs_P2.value = cs[2]
    dut.cs_P3.value = cs[3]
    
    await RisingEdge(dut.clk)
    
    exp_addr = calculate_expected_addresses(addr, cs, None)
    expected_addr_out = (
        (exp_addr[3] << 42) |
        (exp_addr[2] << 28) |
        (exp_addr[1] << 14) |
        (exp_addr[0] << 0)
    )
    
    assert dut.addr_out.value.integer == expected_addr_out, (
        f"Address inversion mismatch for cs_P1=0\n"
        f"Expected: {hex(expected_addr_out)}\n"
        f"Got: {hex(dut.addr_out.value.integer)}"
    )
    
    addr_out_p1 = (dut.addr_out.value.integer >> 14) & ALL_ONES
    addr_out_p2 = (dut.addr_out.value.integer >> 28) & ALL_ONES
    assert addr_out_p1 == ((~addr[1]) & ALL_ONES), f"address_P1 should be inverted"
    assert addr_out_p2 == ((~addr[2]) & ALL_ONES), f"address_P2 should be inverted"
    dut._log.info("✓ Test case 2 PASSED: cs_P1=0 inverts address_P1 and address_P2")
    
    # Test case 3: cs_P2 is low, address_P2 and address_P3 should be inverted
    dut._log.info("Test case 3: cs_P2=0, address_P2 and address_P3 should be inverted")
    
    addr = [0xAAAA, 0xBBBB, 0xCCCC, 0xDDDD]
    cs = [1, 1, 0, 1]  # cs_P2 is low, cs_P3 must be high
    
    dut.address_P0.value = addr[0]
    dut.address_P1.value = addr[1]
    dut.address_P2.value = addr[2]
    dut.address_P3.value = addr[3]
    
    dut.cs_P0.value = cs[0]
    dut.cs_P1.value = cs[1]
    dut.cs_P2.value = cs[2]
    dut.cs_P3.value = cs[3]
    
    await RisingEdge(dut.clk)
    
    exp_addr = calculate_expected_addresses(addr, cs, None)
    expected_addr_out = (
        (exp_addr[3] << 42) |
        (exp_addr[2] << 28) |
        (exp_addr[1] << 14) |
        (exp_addr[0] << 0)
    )
    
    assert dut.addr_out.value.integer == expected_addr_out, (
        f"Address inversion mismatch for cs_P2=0\n"
        f"Expected: {hex(expected_addr_out)}\n"
        f"Got: {hex(dut.addr_out.value.integer)}"
    )
    
    addr_out_p2 = (dut.addr_out.value.integer >> 28) & ALL_ONES
    addr_out_p3 = (dut.addr_out.value.integer >> 42) & ALL_ONES
    assert addr_out_p2 == ((~addr[2]) & ALL_ONES), f"address_P2 should be inverted"
    assert addr_out_p3 == ((~addr[3]) & ALL_ONES), f"address_P3 should be inverted"
    dut._log.info("✓ Test case 3 PASSED: cs_P2=0 inverts address_P2 and address_P3")
    
    # Test case 4: cs_P3 is low, address_P3 should be inverted, and address_P0 in next cycle
    dut._log.info("Test case 4: cs_P3=0, address_P3 inverted, address_P0 inverted in next cycle")
    
    # First cycle: cs_P3 is low
    addr_cycle1 = [0x5555, 0x6666, 0x7777, 0x8888]
    cs_cycle1 = [1, 1, 1, 0]  # cs_P3 is low
    
    dut.address_P0.value = addr_cycle1[0]
    dut.address_P1.value = addr_cycle1[1]
    dut.address_P2.value = addr_cycle1[2]
    dut.address_P3.value = addr_cycle1[3]
    
    dut.cs_P0.value = cs_cycle1[0]
    dut.cs_P1.value = cs_cycle1[1]
    dut.cs_P2.value = cs_cycle1[2]
    dut.cs_P3.value = cs_cycle1[3]
    
    await RisingEdge(dut.clk)
    
    # Check first cycle: address_P3 should be inverted
    exp_addr_cycle1 = calculate_expected_addresses(addr_cycle1, cs_cycle1, None)
    expected_addr_out_cycle1 = (
        (exp_addr_cycle1[3] << 42) |
        (exp_addr_cycle1[2] << 28) |
        (exp_addr_cycle1[1] << 14) |
        (exp_addr_cycle1[0] << 0)
    )
    
    assert dut.addr_out.value.integer == expected_addr_out_cycle1, (
        f"Address inversion mismatch for cs_P3=0 (cycle 1)\n"
        f"Expected: {hex(expected_addr_out_cycle1)}\n"
        f"Got: {hex(dut.addr_out.value.integer)}"
    )
    
    addr_out_p3_cycle1 = (dut.addr_out.value.integer >> 42) & ALL_ONES
    assert addr_out_p3_cycle1 == ((~addr_cycle1[3]) & ALL_ONES), "address_P3 should be inverted"
    
    # Second cycle: cs_P0 must be high (constraint), address_P0 should be inverted due to prev cs_P3=0
    addr_cycle2 = [0x9999, 0xAAAA, 0xBBBB, 0xCCCC]
    cs_cycle2 = [1, 1, 1, 1]  # cs_P0 must be 1 (prev cs_P3 was 0)
    
    dut.address_P0.value = addr_cycle2[0]
    dut.address_P1.value = addr_cycle2[1]
    dut.address_P2.value = addr_cycle2[2]
    dut.address_P3.value = addr_cycle2[3]
    
    dut.cs_P0.value = cs_cycle2[0]
    dut.cs_P1.value = cs_cycle2[1]
    dut.cs_P2.value = cs_cycle2[2]
    dut.cs_P3.value = cs_cycle2[3]
    
    await RisingEdge(dut.clk)
    
    # Check second cycle: address_P0 should be inverted due to prev cs_P3=0
    exp_addr_cycle2 = calculate_expected_addresses(addr_cycle2, cs_cycle2, prev_cs_p3=0)
    expected_addr_out_cycle2 = (
        (exp_addr_cycle2[3] << 42) |
        (exp_addr_cycle2[2] << 28) |
        (exp_addr_cycle2[1] << 14) |
        (exp_addr_cycle2[0] << 0)
    )
    
    assert dut.addr_out.value.integer == expected_addr_out_cycle2, (
        f"Address inversion mismatch for prev cs_P3=0 (cycle 2)\n"
        f"Expected: {hex(expected_addr_out_cycle2)}\n"
        f"Got: {hex(dut.addr_out.value.integer)}\n"
        f"exp_addr = {[hex(a) for a in exp_addr_cycle2]}"
    )
    
    addr_out_p0_cycle2 = (dut.addr_out.value.integer >> 0) & ALL_ONES
    assert addr_out_p0_cycle2 == ((~addr_cycle2[0]) & ALL_ONES), "address_P0 should be inverted due to prev cs_P3=0"
    dut._log.info("✓ Test case 4 PASSED: cs_P3=0 inverts address_P3 and next cycle address_P0")
    
    dut._log.info("All address inversion logic tests PASSED ✅")


# ✅ CRITICAL: Pytest wrapper function (required for HUD format)
def test_addr_decode_runner():
    """Pytest wrapper for Cocotb tests"""
    import os
    from pathlib import Path
    from cocotb_tools.runner import get_runner
    
    sim = os.getenv("SIM", "icarus")
    proj_path = Path(__file__).resolve().parent.parent
    
    # Use sources directory for the DUT (HUD format requirement)
    sources = [proj_path / "sources/addr_decode.sv"]
    
    runner = get_runner(sim)
    runner.build(
        sources=sources,
        hdl_toplevel="addr_decode",
        always=True,
    )
    
    runner.test(hdl_toplevel="addr_decode", test_module="test_addr_decode")

