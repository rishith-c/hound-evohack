"""Limited geometry checks, intentionally distinct from physical-system validation."""
import json
from pathlib import Path
from build123d import Pos, import_step
import rover

root=Path(__file__).parent
assembly=rover.build()
parts={p.label:p for p in assembly.children}
checks=[]

def volume(shape):
    if shape is None:
        return 0.0
    if hasattr(shape,'volume'):
        return shape.volume
    return sum(volume(s) for s in shape)

def check(name, passed, **data):
    checks.append({'check':name,'passed':bool(passed),**data})

check('all generated solids valid',all(s.is_valid and s.volume>0 for s in assembly.solids()),solid_count=len(assembly.solids()))
for name,s in rover.custom_parts().items():
    check(name+' is one valid solid',s.is_valid and len(s.solids())==1,volume_mm3=s.volume)

for name_a,name_b in [
    ('front_left_motor','front_left_mount'),
    ('front_left_motor','2020_side_1'),
    ('front_left_mount','front_left_mecanum'),
    ('front_right_motor','front_right_mount'),
    ('front_right_motor','2020_side_-1'),
    ('fifth_motor_sweep','sweep_bridge_sheet_or_split_print'),
    ('sweep_motor_support','sweep_bridge_sheet_or_split_print'),
    ('idler_support','sweep_bridge_sheet_or_split_print'),
    ('sensor_carriage','MGN12H_carriage_envelope'),
]:
    a,b=parts[name_a],parts[name_b]
    v=volume(a.intersect(b))
    check(name_a+' / '+name_b+' no material overlap',v<0.01,overlap_mm3=v,distance_mm=a.distance_to(b))

# Check the moving head at both ends and the middle of the 200 mm baseline.
moving=[parts['sensor_carriage'],parts['LD2410C_radar_-17_envelope'],parts['LD2410C_radar_17_envelope']]
obstacles=[parts[n] for n in ['mast_column_-125','mast_column_125','sweep_bridge_sheet_or_split_print',
                            'sweep_limit_switch_-143','sweep_limit_switch_143','fifth_motor_sweep']]
for y in (-100,0,100):
    worst=max(volume((Pos(0,y,0)*a).intersect(b)) for a in moving for b in obstacles)
    check('head clearance at sweep '+str(y)+'mm',worst<0.01,worst_overlap_mm3=worst)

b=assembly.bounding_box()
check('model nominal envelope',b.size.X<=351 and b.size.Y<=530 and b.size.Z<=281,
      min=list(b.min),max=list(b.max),size=list(b.size))
step=import_step(root/'rover.step')
check('STEP roundtrip has valid solids',all(s.is_valid and s.volume>0 for s in step.solids()),solid_count=len(step.solids()))
# Compound.volume can deduplicate shared repeated topology in the source assembly.
# Sum occurrence solids on both sides to compare the same quantity.
source_volumes=sorted(s.volume for s in assembly.solids())
step_volumes=sorted(s.volume for s in step.solids())
check('STEP roundtrip occurrence volumes match source',
      len(step_volumes)==len(source_volumes) and all(abs(a-b)<0.01 for a,b in zip(source_volumes,step_volumes)),
      difference_mm3=sum(step_volumes)-sum(source_volumes))
report={'cad_checks_passed':all(c['passed'] for c in checks),'physical_build_gate':'NOT PASSED',
        'detection_validation':'NOT RUN','checks':checks,
        'limits':['Targeted pairs only, not exhaustive interference checking',
                  'Wheel rollers, bearings and purchased interfaces are illustrative',
                  'Motor dynamic torque, electronics, battery, FDM and sensing are unverified']}
(root/'cad-verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['cad_checks_passed'] else 1)
