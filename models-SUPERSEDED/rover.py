"""Mecanum human-presence demonstrator. Units mm; +X forward, +Y left, +Z up.

CONCEPT CAD ONLY. Bought-part envelopes and wheel interfaces require measurement.
No claim of rubble traversal, through-rubble detection, or build approval.
"""
from pathlib import Path
import math
from build123d import (Box, Cylinder, Cone, Compound, Color, Pos, Rot, Plane,
                      BuildSketch, Polygon, extrude, fillet, Axis, export_step,
                      export_stl, Vector)

RAIL_LENGTH = 350.0
RAIL_SIZE = 20.0
RAIL_SLOT = 6.0
FRAME_Z = 85.0
WHEEL_RADIUS = 50.0
WHEEL_WIDTH = 40.0
WHEELBASE = 250.0
TRACK = 480.0
MOTOR_SIZE = 42.3
MOTOR_LENGTH = 39.5
MOTOR_FACE_Y = 204.0
MOTOR_PITCH = 31.0
MOTOR_PILOT_D = 22.2
M3_HOLE = 3.2
M5_HOLE = 5.2
MOUNT_T = 6.0
DECK_Z = 104.0
DECK_T = 4.0
SWEEP_TRAVEL = 200.0
SWEEP_Y = 0.0
SWEEP_BEAM_Z = 208.0
BATTERY_SIZE = (110.0, 40.0, 30.0)  # Unmeasured reservation, not an identified pack.
SILVER = (0.66, 0.70, 0.74)
GREY = (0.38, 0.43, 0.49)
LIGHT = (0.70, 0.73, 0.77)
BLACK = (0.10, 0.12, 0.15)
RUBBER = (0.19, 0.21, 0.24)
GREEN = (0.10, 0.36, 0.24)
RED = (0.66, 0.13, 0.12)
BLUE = (0.14, 0.28, 0.45)
GOLD = (0.72, 0.58, 0.23)


def box(dx, dy, dz, x=0, y=0, z=0):
    return Pos(x, y, z) * Box(dx, dy, dz)


def cyl(radius, length, x=0, y=0, z=0, rotation=(0, 0, 0)):
    return Pos(x, y, z) * Rot(*rotation) * Cylinder(radius, length)


def named(shape, label, rgb):
    shape.label = label
    shape.color = Color(*rgb)
    return shape


def rail(length):
    """Simplified four-slot 2020 profile; actual slot-root shape is unmeasured."""
    s = Box(20, 20, length) - Cylinder(2.5, length + 2)
    for angle in (0, 90, 180, 270):
        cut = box(RAIL_SLOT, 5, length + 2, 0, 8.5)
        s -= Rot(0, 0, angle) * cut
    return s


def motor():
    """Exact-model external envelope, local flange at z=0, shaft towards +Z."""
    body = box(MOTOR_SIZE, MOTOR_SIZE, MOTOR_LENGTH - 8, z=-MOTOR_LENGTH / 2)
    end_a = box(MOTOR_SIZE, MOTOR_SIZE, 4, z=-2)
    end_b = box(MOTOR_SIZE, MOTOR_SIZE, 4, z=-MOTOR_LENGTH + 2)
    pilot = cyl(11, 2, z=1)
    shaft = cyl(2.5, 24, z=12) - box(4, 6, 22, x=4.0, z=12)
    return Compound(label="JK42HS40-1704-13A_envelope", children=[
        named(body, "motor_laminations", BLACK),
        named(end_a + pilot, "front_flange", SILVER),
        named(end_b, "rear_flange", SILVER),
        named(shaft, "5mm_D_shaft", SILVER),
    ])


def motor_mount():
    # Local motor face: Y=0, axle Z=0. Rail top is Z=45.
    s = box(54, MOUNT_T, 78, y=3, z=12)
    s += box(54, 40, MOUNT_T, y=-14, z=48)
    # External ribs avoid motor envelope. Neither bed face is chamfered.
    for x in (-24.5, 24.5):
        with BuildSketch(Plane.YZ.offset(x - 2.5)) as sk:
            Polygon((-29, 45), (0, 45), (0, 16), align=None)
        s += extrude(sk.sketch, amount=5)
    # Fillet only vertical outside corners, before subtracting critical holes.
    try:
        candidates = [e for e in s.edges().filter_by(Axis.Z) if e.length > 60]
        if candidates:
            s = fillet(candidates, radius=1.2)
    except ValueError:
        pass  # The concept records fillet verification separately.
    s -= cyl(MOTOR_PILOT_D / 2, 10, y=3, rotation=(90, 0, 0))
    for x in (-MOTOR_PITCH / 2, MOTOR_PITCH / 2):
        for z in (-MOTOR_PITCH / 2, MOTOR_PITCH / 2):
            s -= cyl(M3_HOLE / 2, 10, x=x, y=3, z=z, rotation=(90, 0, 0))
    for x in (-17, 17):
        # M5 slots allow lateral clamp alignment to measured rail slots.
        cutter = box(M5_HOLE, 7, 10, x=x, y=-19, z=48)
        for y in (-22.5, -15.5):
            cutter += cyl(M5_HOLE / 2, 10, x=x, y=y, z=48)
        s -= cutter
    return s


def hub():
    # Concept custom wheel-side flange: four M3 on a 16 mm square.
    s = cyl(9, 15, z=7.5) + cyl(15, 4, z=17)
    bore = cyl(2.6, 23, z=9.5) - box(5, 8, 25, x=4.65, z=9.5)
    s -= bore
    for x in (-8, 8):
        for y in (-8, 8):
            s -= cyl(M3_HOLE / 2, 8, x=x, y=y, z=17)
    s -= cyl(1.6, 15, x=5, z=7, rotation=(0, 90, 0))
    # Side pocket for a retained M3 nut; threads are not assumed in printed PLA.
    s -= box(3, 5.7, 5.7, x=5.7, z=7)
    return s


def wheel(hand):
    """Illustrative 45-degree roller wheel, axle +Y; supplier interface not selected."""
    core = cyl(28, 22, rotation=(90, 0, 0)) - cyl(3, 30, rotation=(90, 0, 0))
    parts = [named(core, "wheel_core", BLUE)]
    for side in (-1, 1):
        plate=cyl(31, 3, y=side * 12.5, rotation=(90, 0, 0))
        plate-=cyl(3,40,rotation=(90,0,0))
        for x in (-8,8):
            for z in (-8,8):
                plate-=cyl(M3_HOLE/2,40,x=x,z=z,rotation=(90,0,0))
        parts.append(named(plate, "wheel_side_plate", SILVER))
    for i in range(8):
        angle = i * 45
        # Roller at top before rotating around axle; axis lies in X/Y at 45°.
        roller = Cylinder(10, 20)
        roller += Pos(0, 0, 14) * Cone(10, 4, 8)
        roller += Pos(0, 0, -14) * Cone(4, 10, 8)
        roller -= Cylinder(2.2,40)
        placement = Rot(0, angle, 0) * Pos(0, 0, 40) * Rot(0, 0, hand * 45) * Rot(90, 0, 0)
        roller = placement * roller
        parts.append(named(roller, f"free_roller_{i+1}", RUBBER))
        parts.append(named(placement*Cylinder(2,38), f"roller_axle_{i+1}", SILVER))
        for end in (-1,1):
            theta=math.radians(angle)
            dx=hand*end*19/math.sqrt(2)
            y=-end*19/math.sqrt(2)
            a=Vector(26*math.sin(theta),y,26*math.cos(theta))
            b=Vector(dx*math.cos(theta)+40*math.sin(theta),y,-dx*math.sin(theta)+40*math.cos(theta))
            strut=Plane(origin=(a+b)*0.5,z_dir=b-a).location * Cylinder(2.5,(b-a).length)
            parts.append(named(strut,f"roller_support_{i+1}_{end}",SILVER))
    return Compound(label=f"mecanum_{'left' if hand>0 else 'right'}_illustrative", children=parts)


def deck_tile():
    s = Box(170, 170, DECK_T)
    for x in (-65, -45, -25, -5, 15, 35, 55):
        s -= box(7, 62, 8, x=x, y=20)
    for x in (-77.5, 77.5):
        for y in (-57.5, 57.5):
            s -= cyl(M5_HOLE / 2, 10, x=x, y=y)
    for x in (-65, 65):
        for y in (-70, 70):
            s -= cyl(M3_HOLE / 2, 10, x=x, y=y)
    for x in (-75.5,75.5):
        for y in (-75.5,75.5):
            s -= cyl(M3_HOLE/2,10,x=x,y=y)
    return s


def deck_joiner():
    s=Box(40,40,4)
    for x in (-12,12):
        for y in (-12,12):
            s-=cyl(M3_HOLE/2,8,x=x,y=y)
    return s


def battery_cradle():
    bx, by, bz = BATTERY_SIZE
    s = box(bx+12, by+12, 4, z=2)
    for side in (-1, 1):
        wall = box(bx+12, 4, 17, y=side*(by/2+4), z=10.5)
        for x in (-35, 35):
            wall -= box(15, 8, 4, x=x, y=side*(by/2+4), z=7)
        s += wall
        s += box(4, by+4, 13, x=side*(bx/2+4), z=8.5)
    return s


def gusset():
    with BuildSketch() as sk:
        Polygon((0,0), (42,0), (0,42), align=None)
    s = extrude(sk.sketch, amount=5)
    for x,y in ((10,10),(30,10),(10,30)):
        s -= cyl(M5_HOLE/2, 9, x=x, y=y, z=2.5)
    return s


def mast():
    s = box(36,32,5,z=2.5) + box(14,18,91,z=50.5)
    s += box(36,32,5,z=98.5)
    for x in (-12,12):
        s -= cyl(M5_HOLE/2,110,x=x,z=50)
    return s


def carriage():
    s = box(64,62,5,x=-14,z=2.5)
    # Sensor plate at front, open RF face, no metal cover over antennas.
    s += box(5,62,38,x=15.5,z=21)
    for y in (-25,25):
        with BuildSketch(Plane.XZ.offset(-y-2)) as sk:
            Polygon((-12,5),(13,5),(13,30),align=None)
        s += extrude(sk.sketch,amount=4)
    for x in (-10,10):
        for y in (-10,10):
            s -= cyl(M3_HOLE/2,12,x=x,y=y,z=2.5)
    # Two tie slots per radar, avoiding invented radar mounting-hole locations.
    for y in (-17,17):
        for z in (10,31):
            s -= box(10,10,2,x=15.5,y=y,z=z)
    s += box(10,16,9,x=-41,z=-2)
    return s


def tray():
    s = box(100,88,4,z=2)
    # Provisional Uno rectangular board envelope secured by straps, no false PCB pattern.
    for x in (-40,40):
        s -= box(6,64,8,x=x,z=2)
    for x in (-33,33):
        for y in (-24,24):
            s += cyl(4,8,x=x,y=y,z=8)
            s -= cyl(1.6,18,x=x,y=y,z=8)
    return s


def custom_parts():
    return {"motor_mount":motor_mount(), "wheel_hub":hub(), "deck_tile":deck_tile(),
            "battery_cradle":battery_cradle(), "corner_gusset":gusset(),
            "mast_column":mast(), "sensor_carriage":carriage(), "electronics_tray":tray(),
            "deck_joiner":deck_joiner()}


def build(exploded=False):
    parts=[]
    def add(s,label,color,pos=(0,0,0),rot=(0,0,0),explode=(0,0,0)):
        p=tuple(a+(b if exploded else 0) for a,b in zip(pos,explode))
        shape=Pos(*p)*Rot(*rot)*s
        shape.label=label
        if not isinstance(shape,Compound) or not shape.children:
            shape.color=Color(*color)
        parts.append(shape)
    for side in (-1,1):
        add(rail(RAIL_LENGTH),f"2020_side_{side}",SILVER,(0,side*185,FRAME_Z),(0,90,0))
        add(rail(RAIL_LENGTH),f"2020_cross_{side}",SILVER,(side*165,0,FRAME_Z),(90,0,0))
    for x in (-WHEELBASE/2,WHEELBASE/2):
        for side in (-1,1):
            wheel_name=('front' if x>0 else 'rear')+('_left' if side>0 else '_right')
            hand=-1 if (x>0)==(side>0) else 1
            add(motor(),wheel_name+'_motor',BLACK,(x,side*MOTOR_FACE_Y,WHEEL_RADIUS),(-side*90,0,0),explode=(0,side*30,0))
            add(motor_mount(),wheel_name+'_mount',GREY,(x,side*MOTOR_FACE_Y,WHEEL_RADIUS),(0,0,0 if side>0 else 180),explode=(0,side*60,15))
            add(hub(),wheel_name+'_hub_interface_TBD',SILVER,(x,side*207,WHEEL_RADIUS),(-side*90,0,0),explode=(0,side*95,0))
            add(wheel(hand),wheel_name+'_mecanum',BLUE,(x,side*TRACK/2,WHEEL_RADIUS),explode=(0,side*140,0))
    for x in (-87.5,87.5):
        for y in (-87.5,87.5):
            add(deck_tile(),f"deck_tile_{x}_{y}",LIGHT,(x,y,DECK_Z+2),explode=(0,0,50))
    add(deck_joiner(),"deck_center_joiner",GREY,(0,0,102),explode=(0,0,30))
    # Deck supports contact cross rails; seam hardware is reserved, not fully detailed.
    for x in (-165,165):
        for y in (-145,145):
            spacer=cyl(5,9,z=4.5)-cyl(M5_HOLE/2,11,z=4.5)
            add(spacer,f"deck_spacer_{x}_{y}",SILVER,(x,y,95))
    for x in (-150,150):
        for y in (-170,170):
            add(gusset(),f"frame_gusset_{x}_{y}",GREY,(x,y,95),rot=(0,0,180 if x>0 else 0))
    add(battery_cradle(),"battery_cradle",GREY,(-70,0,108),explode=(0,0,90))
    add(box(*BATTERY_SIZE),"11V1_battery_UNMEASURED",BLACK,(-70,0,127),explode=(0,0,150))
    add(tray(),"Uno_tray",GREY,(0,-95,108),explode=(0,0,90))
    add(box(68.6,53.4,1.6),"Uno_R3_envelope",GREEN,(0,-95,120.8),explode=(0,0,140))
    add(box(69,54,1.6),"CNC_Shield_V3_envelope",RED,(0,-95,138),explode=(0,0,165))
    for x in (-24,-8,8,24):
        add(box(15,20,9),f"A4988_{x}_envelope",GREEN,(x,-95,145),explode=(0,0,175))
        add(box(10,10,8),f"driver_heatsink_{x}",SILVER,(x,-95,154),explode=(0,0,185))
    add(box(85,56,1.6),"Raspberry_Pi_4_envelope_MODEL_TBD",GREEN,(-92,93,119),explode=(0,0,140))
    add(box(22,30,13),"Pi_USB_envelope",SILVER,(-60,93,126),explode=(0,0,140))
    tb=box(96,71,28)
    add(tb,"TB6600_envelope_MODEL_TBD",BLACK,(25,75,126),explode=(0,0,110))
    for i in range(9):
        add(box(90,2,9),f"TB6600_fin_{i}",BLACK,(25,47+i*7,144.5),explode=(0,0,110))
    add(box(40,40,10)-cyl(16,12),"driver_fan_reservation",BLACK,(0,-95,180),explode=(0,0,170))
    # Fan mounting posts are explicit; exact fan wiring and hole pitch require confirmation.
    for x in (-17,17):
        for y in (-112,-78):
            add(cyl(3,35,z=17.5)-cyl(1.6,37,z=17.5),f"fan_post_{x}_{y}",GREY,(x,y,140),explode=(0,0,120))
    for y in (-145,145):
        add(box(51,26,2),f"ESP32_S3_devboard_envelope_{y}",GREEN,(-90,y,118),explode=(0,0,130))
    add(box(45,25,14),"5V_converter_reservation",GREEN,(-140,-62,118),explode=(0,0,110))
    add(box(24,18,14),"fuse_and_cutoff_reservation",BLACK,(-140,20,118),explode=(0,0,110))
    add(cyl(12,8),"stop_button_reservation",RED,(-145,142,120),explode=(0,0,120))
    for y in (-125,125):
        add(mast(),f"mast_column_{y}",GREY,(110,y,108),explode=(0,0,140))
    beam=box(30,330,10)
    for y in (-125,125):
        for x in (-12,12):
            beam-=cyl(M5_HOLE/2,14,x=x,y=y)
    add(beam,"sweep_bridge_sheet_or_split_print",SILVER,(110,0,214),explode=(0,0,190))
    add(box(12,300,8),"MGN12_300mm_guide_envelope",SILVER,(110,0,223),explode=(0,0,205))
    add(box(27,45.4,10),"MGN12H_carriage_envelope",BLACK,(110,SWEEP_Y,232),explode=(0,0,235))
    add(carriage(),"sensor_carriage",GREY,(110,SWEEP_Y,237),explode=(0,0,265))
    for y in (-17,17):
        add(box(1.6,22,23),f"LD2410C_radar_{y}_envelope",GREEN,(130,SWEEP_Y+y,258),explode=(0,0,290))
        add(box(1,16,12),f"24GHz_antenna_face_{y}",GOLD,(131.3,SWEEP_Y+y,258),explode=(0,0,290))
    # Sweep motor has its own support tied into the bridge.
    support=box(62,54,6,x=-8)+box(35,30,6,x=36)
    support-=cyl(11.1,10,x=-8)
    for x in (-15.5,15.5):
        for y in (-15.5,15.5):
            support-=cyl(M3_HOLE/2,10,x=x-8,y=y)
    add(support,"sweep_motor_support",GREY,(72,-150,222),explode=(0,0,190))
    add(motor(),"fifth_motor_sweep",BLACK,(64,-150,219),explode=(0,0,155))
    for y in (-150,150):
        pulley=cyl(6.37,7)+cyl(8,1,z=4)+cyl(8,1,z=-4)
        add(pulley,f"GT2_20T_pulley_envelope_{y}",SILVER,(64,y,232),explode=(0,0,235))
    idler=box(60,25,6)-cyl(3.2,10,x=-21)
    add(idler,"idler_support",GREY,(85,150,222),explode=(0,0,190))
    add(cyl(3,13),"idler_axle",SILVER,(64,150,224.5),explode=(0,0,210))
    for x in (57.63,70.37):
        add(box(1.4,300,6),f"GT2_belt_run_{x}",BLACK,(x,0,232),explode=(0,0,235))
    for side in (-1,1):
        arc=(cyl(7.07,6)-cyl(5.67,8)) & box(20,10,10,y=side*5)
        add(arc,f"GT2_belt_wrap_{side}",BLACK,(64,side*150,232),explode=(0,0,235))
    for y in (-143,143):
        add(box(12,6,8),f"sweep_limit_switch_{y}",BLACK,(110,y,235),explode=(0,0,225))
    return Compound(label="Mecanum_presence_rover_CONCEPT"+('_exploded' if exploded else ''),children=parts)


def gen_step():
    return build()


if __name__ == '__main__':
    root=Path(__file__).parent/'parts'
    root.mkdir(exist_ok=True)
    for label,shape in custom_parts().items():
        shape.label=label
        export_step(shape,root/(label+'.step'))
        export_stl(shape,root/(label+'.stl'))
        print(label,'valid',shape.is_valid,'solids',len(shape.solids()),'mm3',round(shape.volume,2))
