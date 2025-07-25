"""
Missing Section Detection Demo

This demonstrates the enhanced well path tracer's ability to detect when
well paths exit into areas where section data is missing, and provide
specific recommendations for adding new sections.
"""

import pandas as pd
import numpy as np
from shapely.geometry import Point, LineString, Polygon
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple
import warnings

warnings.filterwarnings('ignore')


def create_scenario_with_missing_sections():
    """
    Create a test scenario where the well path clearly exits into areas
    where section data is missing
    """

    # Create two known sections with a gap between them
    sections_data = []

    # Section 1: 0107S19ES (Western section)
    section1_data = {
        'conc': ['0107S19ES'] * 20,
        'side': ['west', 'west', 'west', 'west', 'west',
                 'north', 'north', 'north', 'north', 'north',
                 'east', 'east', 'east', 'east', 'east',
                 'south', 'south', 'south', 'south', 'south'],
        'point_i': [0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4],
        'x': [0.0, 500.0, 1000.0, 1500.0, 2000.0,
              2000.0, 2500.0, 3000.0, 3500.0, 4000.0,
              4000.0, 3500.0, 3000.0, 2500.0, 2000.0,
              2000.0, 1500.0, 1000.0, 500.0, 0.0],
        'y': [0.0, 0.0, 0.0, 0.0, 0.0,
              0.0, 500.0, 1000.0, 1500.0, 2000.0,
              2000.0, 2500.0, 3000.0, 3500.0, 4000.0,
              4000.0, 4000.0, 4000.0, 4000.0, 4000.0]
    }
    sections_data.append(pd.DataFrame(section1_data))

    # Section 3: 0107S19ET (Eastern section - note the gap where section 2 should be)
    section3_data = {
        'conc': ['0107S19ET'] * 20,
        'side': ['west', 'west', 'west', 'west', 'west',
                 'north', 'north', 'north', 'north', 'north',
                 'east', 'east', 'east', 'east', 'east',
                 'south', 'south', 'south', 'south', 'south'],
        'point_i': [0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4],
        'x': [8000.0, 8500.0, 9000.0, 9500.0, 10000.0,
              10000.0, 10500.0, 11000.0, 11500.0, 12000.0,
              12000.0, 11500.0, 11000.0, 10500.0, 10000.0,
              10000.0, 9500.0, 9000.0, 8500.0, 8000.0],
        'y': [0.0, 0.0, 0.0, 0.0, 0.0,
              0.0, 500.0, 1000.0, 1500.0, 2000.0,
              2000.0, 2500.0, 3000.0, 3500.0, 4000.0,
              4000.0, 4000.0, 4000.0, 4000.0, 4000.0]
    }
    sections_data.append(pd.DataFrame(section3_data))

    # Combine sections
    all_sections_df = pd.concat(sections_data, ignore_index=True)

    # Create well path that travels from section 1, through missing area, to section 3
    well_path_points = []

    # Start in section 1
    for i in range(20):
        x = 1000 + i * 50
        y = 2000 + i * 20
        well_path_points.append((x, y))

    # Exit section 1 and travel through missing section area
    for i in range(40):
        x = 2000 + i * 150  # Travel east through gap
        y = 2400 + i * 10
        well_path_points.append((x, y))

    # Enter section 3
    for i in range(20):
        x = 8000 + i * 50
        y = 2800 + i * 15
        well_path_points.append((x, y))

    # Create well path DataFrame
    well_data = []
    for i, (x, y) in enumerate(well_path_points):
        well_data.append({
            'e_offset_delta': x,
            'n_offset_delta': y,
            'easting': x + 552265,
            'northing': y + 4443487,
            'point_index': i
        })

    return all_sections_df, pd.DataFrame(well_data)


def create_complex_missing_section_scenario():
    """
    Create a more complex scenario with multiple missing sections and re-entries
    """

    # Create a grid of sections with gaps
    sections_data = []
    section_size = 4000

    # Create sections at positions (0,0), (0,1), (1,1), leaving gaps at (1,0) and (0,2)
    section_positions = [
        (0, 0, "0107S19ES"),  # Southwest
        (0, 1, "0106S19ES"),  # Northwest
        (1, 1, "0106S19ET"),  # Northeast
        # Missing: (1, 0) "0107S19ET" - Southeast
        # Missing: (0, 2) "0105S19ES" - Far Northwest
    ]

    for grid_x, grid_y, section_id in section_positions:
        base_x = grid_x * section_size
        base_y = grid_y * section_size

        section_data = {
            'conc': [section_id] * 20,
            'side': ['west', 'west', 'west', 'west', 'west',
                     'north', 'north', 'north', 'north', 'north',
                     'east', 'east', 'east', 'east', 'east',
                     'south', 'south', 'south', 'south', 'south'],
            'point_i': [0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4],
            'x': [base_x, base_x + 1000, base_x + 2000, base_x + 3000, base_x + 4000,
                  base_x + 4000, base_x + 4000, base_x + 4000, base_x + 4000, base_x + 4000,
                  base_x + 4000, base_x + 3000, base_x + 2000, base_x + 1000, base_x,
                  base_x, base_x, base_x, base_x, base_x],
            'y': [base_y, base_y, base_y, base_y, base_y,
                  base_y, base_y + 1000, base_y + 2000, base_y + 3000, base_y + 4000,
                  base_y + 4000, base_y + 4000, base_y + 4000, base_y + 4000, base_y + 4000,
                  base_y + 4000, base_y + 3000, base_y + 2000, base_y + 1000, base_y]
        }
        sections_data.append(pd.DataFrame(section_data))

    all_sections_df = pd.concat(sections_data, ignore_index=True)

    # Create complex well path that exposes multiple missing sections
    well_path_points = []

    # Start in 0107S19ES (0,0)
    for i in range(15):
        x = 500 + i * 100
        y = 2000 + i * 50
        well_path_points.append((x, y))

    # Exit east into missing section (1,0) - "0107S19ET"
    for i in range(25):
        x = 2000 + i * 120
        y = 2750 + i * 20
        well_path_points.append((x, y))

    # Continue into existing section (1,1) - "0106S19ET"
    for i in range(20):
        x = 5000 + i * 80
        y = 3250 + i * 40
        well_path_points.append((x, y))

    # Exit north into missing section (0,2) area
    for i in range(30):
        x = 6600 - i * 80
        y = 4000 + i * 100
        well_path_points.append((x, y))

    # Re-enter known section (0,1) - "0106S19ES"
    for i in range(15):
        x = 4200 - i * 100
        y = 7000 + i * 30
        well_path_points.append((x, y))

    # Create well path DataFrame
    well_data = []
    for i, (x, y) in enumerate(well_path_points):
        well_data.append({
            'e_offset_delta': x,
            'n_offset_delta': y,
            'easting': x + 552265,
            'northing': y + 4443487,
            'point_index': i
        })

    return all_sections_df, pd.DataFrame(well_data)


def visualize_missing_section_analysis(sections_df: pd.DataFrame,
                                       well_path_df: pd.DataFrame,
                                       tracer_result,
                                       title: str = "Missing Section Detection Analysis"):
    """
    Create comprehensive visualization showing missing section alerts
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))

    # Left plot: Full overview
    ax = ax1

    # Plot existing sections
    for section_id in sections_df['conc'].unique():
        section_data = sections_df[sections_df['conc'] == section_id]

        coords = [(row['x'], row['y']) for _, row in section_data.iterrows()]
        if len(coords) > 2:
            polygon = Polygon(coords)
            if polygon.is_valid:
                x_coords, y_coords = polygon.exterior.xy
                ax.plot(x_coords, y_coords, 'b-', linewidth=2, alpha=0.7)
                ax.fill(x_coords, y_coords, alpha=0.3, color='lightblue')

                centroid = polygon.centroid
                ax.text(centroid.x, centroid.y, section_id,
                        ha='center', va='center', fontsize=9, fontweight='bold')

    # Plot well path
    x_coords = well_path_df['e_offset_delta'].values
    y_coords = well_path_df['n_offset_delta'].values
    ax.plot(x_coords, y_coords, 'r-', linewidth=3, alpha=0.8, label='Well Path')

    # Mark start and end
    ax.plot(x_coords[0], y_coords[0], 'go', markersize=10, label='Start')
    ax.plot(x_coords[-1], y_coords[-1], 'rs', markersize=10, label='End')

    # Highlight untraced segments
    if tracer_result.untraced_segments:
        for i, segment in enumerate(tracer_result.untraced_segments):
            seg_coords = list(segment.coords)
            seg_x = [coord[0] for coord in seg_coords]
            seg_y = [coord[1] for coord in seg_coords]
            ax.plot(seg_x, seg_y, 'orange', linewidth=5, alpha=0.7,
                    label='Untraced Segment' if i == 0 else "")

    # Show missing section alerts
    if tracer_result.missing_section_alerts:
        for i, alert in enumerate(tracer_result.missing_section_alerts):
            # Mark suggested location
            ax.plot(alert.suggested_location.x, alert.suggested_location.y,
                    'r*', markersize=15, label='Missing Section Alert' if i == 0 else "")

            # Add text annotation
            ax.annotate(f'Missing\nSection #{i + 1}',
                        xy=(alert.suggested_location.x, alert.suggested_location.y),
                        xytext=(10, 10), textcoords='offset points',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7),
                        fontsize=8, ha='left')

            # Draw arrow from exit point to suggested location
            ax.annotate('', xy=(alert.suggested_location.x, alert.suggested_location.y),
                        xytext=(alert.exit_point.x, alert.exit_point.y),
                        arrowprops=dict(arrowstyle='->', color='red', lw=2, alpha=0.7))

    ax.set_xlabel('X Coordinate (units)')
    ax.set_ylabel('Y Coordinate (units)')
    ax.set_title('Overview: Well Path and Missing Sections')
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax.grid(True, alpha=0.3)
    ax.set_aspect('equal', adjustable='box')

    # Right plot: Focus on missing section areas
    ax = ax2

    if tracer_result.missing_section_alerts:
        # Focus on the first missing section area
        alert = tracer_result.missing_section_alerts[0]

        # Set view around the missing section
        center_x = alert.suggested_location.x
        center_y = alert.suggested_location.y
        view_size = 6000

        ax.set_xlim(center_x - view_size / 2, center_x + view_size / 2)
        ax.set_ylim(center_y - view_size / 2, center_y + view_size / 2)

        # Plot existing sections in view
        for section_id in sections_df['conc'].unique():
            section_data = sections_df[sections_df['conc'] == section_id]
            coords = [(row['x'], row['y']) for _, row in section_data.iterrows()]
            if len(coords) > 2:
                polygon = Polygon(coords)
                if polygon.is_valid and polygon.intersects(
                        Polygon([(center_x - view_size / 2, center_y - view_size / 2),
                                 (center_x + view_size / 2, center_y - view_size / 2),
                                 (center_x + view_size / 2, center_y + view_size / 2),
                                 (center_x - view_size / 2, center_y + view_size / 2)])):
                    x_coords, y_coords = polygon.exterior.xy
                    ax.plot(x_coords, y_coords, 'b-', linewidth=2)
                    ax.fill(x_coords, y_coords, alpha=0.3, color='lightblue')

                    centroid = polygon.centroid
                    ax.text(centroid.x, centroid.y, section_id,
                            ha='center', va='center', fontsize=10, fontweight='bold')

        # Plot well path in view
        well_mask = ((well_path_df['e_offset_delta'] >= center_x - view_size / 2) &
                     (well_path_df['e_offset_delta'] <= center_x + view_size / 2) &
                     (well_path_df['n_offset_delta'] >= center_y - view_size / 2) &
                     (well_path_df['n_offset_delta'] <= center_y + view_size / 2))

        well_in_view = well_path_df[well_mask]
        if not well_in_view.empty:
            ax.plot(well_in_view['e_offset_delta'], well_in_view['n_offset_delta'],
                    'r-', linewidth=4, alpha=0.8)

        # Highlight the missing section area
        ax.plot(alert.suggested_location.x, alert.suggested_location.y,
                'r*', markersize=20)

        # Draw proposed section boundary (estimated)
        section_size = 4000  # Estimated section size
        proposed_bounds = [
            (alert.suggested_location.x - section_size / 2, alert.suggested_location.y - section_size / 2),
            (alert.suggested_location.x + section_size / 2, alert.suggested_location.y - section_size / 2),
            (alert.suggested_location.x + section_size / 2, alert.suggested_location.y + section_size / 2),
            (alert.suggested_location.x - section_size / 2, alert.suggested_location.y + section_size / 2),
            (alert.suggested_location.x - section_size / 2, alert.suggested_location.y - section_size / 2)
        ]

        prop_x = [coord[0] for coord in proposed_bounds]
        prop_y = [coord[1] for coord in proposed_bounds]
        ax.plot(prop_x, prop_y, 'r--', linewidth=3, alpha=0.7, label='Proposed Section')
        ax.fill(prop_x, prop_y, alpha=0.2, color='red')

        ax.text(alert.suggested_location.x, alert.suggested_location.y - section_size / 3,
                'MISSING\nSECTION', ha='center', va='center',
                fontsize=12, fontweight='bold', color='red')

    ax.set_xlabel('X Coordinate (units)')
    ax.set_ylabel('Y Coordinate (units)')
    ax.set_title('Detail: Missing Section Area')
    ax.grid(True, alpha=0.3)
    ax.set_aspect('equal', adjustable='box')

    plt.tight_layout()
    return fig


def demonstrate_missing_section_detection():
    """
    Run comprehensive demonstration of missing section detection
    """
    print("=" * 80)
    print("MISSING SECTION DETECTION DEMONSTRATION")
    print("=" * 80)

    # Test Case 1: Simple missing section
    print("\n🔍 TEST CASE 1: Simple Missing Section Scenario")
    print("-" * 50)

    sections_df1, well_path_df1 = create_scenario_with_missing_sections()

    # Import and use the enhanced tracer
    from well_path_tracer import WellPathTracer, extract_well_coordinates_from_clearance_data

    tracer = WellPathTracer(tolerance=0.1, debug=True)
    well_path1 = extract_well_coordinates_from_clearance_data(well_path_df1)

    print(f"Created scenario with {len(sections_df1['conc'].unique())} sections")
    print(f"Well path length: {well_path1.length:.2f} units")

    result1 = tracer.trace_well_path(well_path1, sections_df1)

    print(f"\nAnalysis Results:")
    print(f"✓ Sections visited: {len(result1.sections_visited)}")
    print(f"✓ Untraced segments: {len(result1.untraced_segments)}")
    print(f"🚨 Missing section alerts: {len(result1.missing_section_alerts)}")

    if result1.missing_section_alerts:
        print(f"\nMISSING SECTION DETAILS:")
        for i, alert in enumerate(result1.missing_section_alerts, 1):
            print(f"  Alert #{i}:")
            print(f"    Exit from: {alert.exit_section_id} (via {alert.exit_side})")
            print(f"    Trajectory: {alert.trajectory_direction}")
            print(f"    Confidence: {alert.confidence_score:.2f}")
            print(f"    Suggested location: ({alert.suggested_location.x:.0f}, {alert.suggested_location.y:.0f})")

    # Test Case 2: Complex missing sections with re-entries
    print(f"\n🔍 TEST CASE 2: Complex Missing Sections Scenario")
    print("-" * 50)

    sections_df2, well_path_df2 = create_complex_missing_section_scenario()
    well_path2 = extract_well_coordinates_from_clearance_data(well_path_df2)

    print(f"Created complex scenario with {len(sections_df2['conc'].unique())} sections")
    print(f"Well path length: {well_path2.length:.2f} units")

    result2 = tracer.trace_well_path(well_path2, sections_df2)

    print(f"\nComplex Analysis Results:")
    print(f"✓ Sections visited: {len(result2.sections_visited)}")
    print(f"✓ Total visits: {sum(result2.sections_visited.values())}")
    print(f"✓ Re-entries: {sum(result2.sections_visited.values()) - len(result2.sections_visited)}")
    print(f"✓ Untraced segments: {len(result2.untraced_segments)}")
    print(f"🚨 Missing section alerts: {len(result2.missing_section_alerts)}")

    # Generate comprehensive report
    print(f"\n📋 COMPREHENSIVE ANALYSIS REPORT (Test Case 2):")
    print("=" * 60)
    report = tracer.create_traversal_report(result2)
    print(report)

    # Create visualizations
    print(f"\n📊 Creating visualizations...")
    try:
        # Simple scenario
        fig1 = visualize_missing_section_analysis(
            sections_df1, well_path_df1, result1,
            "Simple Missing Section Detection"
        )
        plt.figure(fig1.number)
        plt.savefig('missing_section_simple.png', dpi=300, bbox_inches='tight')

        # Complex scenario
        fig2 = visualize_missing_section_analysis(
            sections_df2, well_path_df2, result2,
            "Complex Missing Section Detection"
        )
        plt.figure(fig2.number)
        plt.savefig('missing_section_complex.png', dpi=300, bbox_inches='tight')

        print("✓ Visualizations saved:")
        print("  - missing_section_simple.png")
        print("  - missing_section_complex.png")

    except Exception as e:
        print(f"✗ Visualization error: {e}")

    return result1, result2


def integration_guidance():
    """
    Provide guidance for integrating missing section detection with existing system
    """
    print("\n" + "=" * 80)
    print("INTEGRATION GUIDANCE FOR EXISTING SYSTEM")
    print("=" * 80)

    print("""
🔧 INTEGRATION STEPS:

1. UPDATE MAIN TRACER CALL:
   Replace your existing main_tracer_process call with enhanced version:

   # OLD:
   tracer_output = self.main_tracer_process(current_plat_coords, current_plat_conc, 
                                           original_all_plats_df, clearance_data, title)

   # NEW:
   from well_path_tracer import enhanced_main_tracer_process
   result = enhanced_main_tracer_process(current_plat_coords, current_plat_conc,
                                        original_all_plats_df, clearance_data, debug=True)

2. HANDLE MISSING SECTION ALERTS:
   Add logic to process missing section alerts:

   if result.missing_section_alerts:
       for alert in result.missing_section_alerts:
           # Show alert to user
           self.show_missing_section_alert(alert)

           # Suggest adding to rel_all_sections_tabs
           next_tab_num = self.get_next_available_tab_number()
           suggested_tab = f"tab_rel_{next_tab_num}"

           # Optionally auto-populate section data
           if alert.confidence_score > 0.7:
               self.suggest_section_addition(alert, suggested_tab)

3. UI INTEGRATION:
   Add missing section alerts to your UI:

   def show_missing_section_alert(self, alert):
       msg = QMessageBox()
       msg.setIcon(QMessageBox.Warning)
       msg.setWindowTitle("Missing Section Detected")
       msg.setText(alert.recommended_action)
       msg.setDetailedText(f"Suggested location: ({alert.suggested_location.x:.0f}, {alert.suggested_location.y:.0f})")
       msg.exec_()

4. AUTO-SECTION GENERATION (Optional):
   For high-confidence alerts, automatically generate section data:

   def auto_generate_section_data(self, alert):
       # Create section coordinates based on alert.suggested_location
       # Use typical section size and orientation
       # Add to next available tab in rel_all_sections_tabs

5. WORKFLOW INTEGRATION:
   Modify your workflow to handle iterative section addition:

   while True:
       result = enhanced_main_tracer_process(...)

       if not result.missing_section_alerts:
           break  # All sections covered

       # Show alerts to user
       # Wait for user to add sections
       # Re-run analysis

🎯 BENEFITS:
✓ Automatically detect missing section coverage
✓ Provide specific location recommendations  
✓ Suggest section IDs based on geometric analysis
✓ Prioritize alerts by confidence score
✓ Integrate seamlessly with existing rel_all_sections_tabs workflow
✓ Reduce manual guesswork in section placement
✓ Ensure complete well path coverage

🔍 TESTING:
- Test with known incomplete section sets
- Verify alert accuracy with field data
- Validate suggested section IDs match surveying conventions
- Confirm integration with existing UI workflow
""")


if __name__ == "__main__":
    print("Missing Section Detection Demo Starting...")

    try:
        # Run demonstrations
        result1, result2 = demonstrate_missing_section_detection()

        # Show integration guidance
        integration_guidance()

        print("\n" + "=" * 80)
        print("✅ MISSING SECTION DETECTION DEMO COMPLETED")
        print("=" * 80)
        print("\nKey Capabilities Demonstrated:")
        print("✓ Automatic detection of well paths exiting into unmapped areas")
        print("✓ Confidence-based alerting system")
        print("✓ Specific location recommendations for new sections")
        print("✓ Section ID suggestions based on geometric analysis")
        print("✓ Integration guidance for existing rel_all_sections_tabs workflow")
        print("✓ Visual analysis tools for validation")

        print(f"\nThe enhanced tracer is ready to eliminate guesswork in section placement!")

    except Exception as e:
        print(f"\nDemo failed: {e}")
        import traceback

        traceback.print_exc()