#!/usr/bin/env python3
"""Original integer-grid artwork. Run with the installed pixel CLI's Pillow environment."""
import json
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
COLORS = dict(ink='#101e28', shade='#183d48', teal='#226274', enamel='#348594', glint='#77b9b0',
              copper='#995737', brass='#d39452', light='#f3c887', eye='#baf5c7', dark='#53382e')
# Explicit six-legged gait poses: foot stride, lifted tripod (A/B), body compression.
GAIT = [(-3, 0, 0), (-1, 0, -1), (2, 0, 0), (3, 1, 0), (1, 1, -1), (-2, 1, 0)]
ACTIONS = {
 'idle': [(0,0,0,0,0,0,0,180),(0,0,0,1,0,0,0,160),(0,0,0,2,0,0,0,180),(0,0,0,1,0,0,0,160)],
 'walk': [(s,l,b,0,0,0,0,110) for s,l,b in GAIT],
 'run': [(s*2,l,b-1,1,0,0,0,65) for s,l,b in GAIT],
 # stride, tripod, body Y, core phase, claw opening, tuck, recoil X, duration.
 'attack': [(0,0,1,0,2,0,-2,130),(0,0,1,2,7,0,-3,170),
            (0,0,-1,2,-1,0,3,70),(0,0,0,1,0,0,1,110),(0,0,0,0,0,0,0,160)],
 'jump': [(0,0,3,0,0,1,0,130),(0,0,-4,2,1,2,0,100),
          (0,0,-6,2,1,3,0,180),(0,0,-3,1,0,2,0,100),(0,0,2,0,0,1,0,140)],
 'hurt': [(0,0,-2,0,4,2,-4,90),(0,0,1,0,2,1,-2,130),(0,0,0,0,0,0,0,180)]}


def pose(spec):
    stride, tripod, bob, pulse, claw, tuck, recoil, _ = spec
    im = Image.new('RGBA',(64,48))
    d = ImageDraw.Draw(im)
    def poly(points, color, outline='ink'):
        d.polygon(points, fill=COLORS[color])
        if outline: d.line(points+[points[0]], fill=COLORS[outline], width=1)
    def line(points, color, width=1): d.line(points, fill=COLORS[color], width=width)
    def rect(box,color): d.rectangle(box,fill=COLORS[color])
    # Rear and foreground legs have separate joints and alternating planted/lifted feet.
    for far in (True,False):
        for j, hipx in enumerate((20,28,36)):
            group=(j+int(far))%2
            lifted=bool(stride and group==tripod)
            s=stride if group==0 else -stride
            hip=(hipx+recoil,29+bob+(0 if far else 2))
            knee=(hipx-5+recoil+s//2,32+bob+(0 if far else 2))
            foot=(hipx-7+s+recoil,38-(4 if lifted else 0)-(2 if far else 0))
            if tuck:
                knee=(hipx-2+recoil,32+bob)
                foot=(hipx+2+recoil,32+bob+max(0,4-tuck*2))
            line([hip,knee,foot], 'ink', 3)
            line([hip,knee,foot], 'copper' if far else 'brass')
            rect((foot[0]-1,foot[1],foot[0]+2,foot[1]+1),'shade' if far else 'light')
        if far:
            # A segmented low body with beveled enamel plates, copper seams, spine gear.
            x,y=recoil,bob
            poly([(14+x,24+y),(17+x,18+y),(23+x,14+y),(33+x,14+y),(41+x,19+y),
                  (43+x,27+y),(38+x,33+y),(20+x,33+y),(15+x,29+y)],'copper')
            poly([(16+x,24+y),(20+x,18+y),(26+x,16+y),(31+x,16+y),(31+x,29+y),(21+x,30+y),(17+x,27+y)],'teal')
            poly([(33+x,16+y),(39+x,20+y),(40+x,26+y),(36+x,30+y),(33+x,29+y)],'shade')
            line([(20+x,20+y),(24+x,17+y),(28+x,17+y)],'glint')
            line([(18+x,25+y),(22+x,23+y),(30+x,23+y)],'enamel')
            line([(19+x,28+y),(30+x,28+y)],'shade')
            line([(32+x,16+y),(32+x,30+y)],'brass')
            for rx,ry in ((20,21),(28,19),(36,22),(27,30)):
                rect((rx+x,ry+y,rx+x,ry+y),'light')
            # Squared winding key, never a humanoid head or limbs.
            line([(24+x,14+y),(24+x,10+y)],'ink',3)
            poly([(20+x,9+y),(23+x,7+y),(26+x,8+y),(29+x,7+y),(30+x,10+y),(26+x,12+y),(22+x,11+y)],'brass')
            rect((23+x+pulse%2,9+y,24+x+pulse%2,10+y),'dark')
            # Eye recessed into the front head and a pulsing exposed power chamber.
            poly([(40+x,22+y),(45+x,21+y),(48+x,24+y),(47+x,29+y),(41+x,29+y)],'shade')
            rect((44+x,23+y,46+x,24+y),'eye')
            rect((35+x,26+y,37+x,28+y),'dark')
            rect((36+x,26+y,36+x+(pulse==2),27+y),'light' if pulse else 'copper')
            # Claw actuator and asymmetric hooked jaws: open telegraph, closed contact.
            line([(44+x,29+y),(49+x,29+y),(51+x,26+y)],'ink',4)
            line([(44+x,29+y),(49+x,29+y),(51+x,26+y)],'brass',2)
            cx=min(3,max(-2,recoil))
            poly([(49+cx,25+y),(51+cx,22+y-claw),(57+cx,21+y-claw),
                  (59+cx,23+y-claw),(55+cx,23+y-claw),(53+cx,26+y)],'copper')
            line([(51+cx,23+y-claw),(56+cx,22+y-claw)],'light')
            poly([(50+cx,28+y),(54+cx,27+y),(56+cx,29+y+claw//2),
                  (59+cx,28+y+claw//2),(57+cx,32+y+claw//2),(52+cx,31+y)],'brass')
            rect((49+cx,26+y,50+cx,27+y),'light')
    return im


def main():
    frames = ROOT/'poses'
    frames.mkdir(exist_ok=True)
    request={'schema_version':1,'cell_size':[64,48],'pivot_px_from_top_left':[29,40], 'actions':{},'events':[]}
    sheet=Image.new('RGB',(6*80,6*72),'#34434b')
    draw=ImageDraw.Draw(sheet)
    views=[]; durations=[]
    for row,(name,specs) in enumerate(ACTIONS.items()):
        entries=[]
        for index,spec in enumerate(specs):
            image=pose(spec)
            assert image.getbbox() and image.getbbox()[0]>0 and image.getbbox()[2]<64 and image.getbbox()[1]>0 and image.getbbox()[3]<48, (name,index,image.getbbox())
            filename=f'poses/{name}-{index:02}.png'
            image.save(ROOT/filename)
            entries.append({'path':filename,'duration_ms':spec[-1]})
            sheet.paste(image,(index*80+8,row*72+16),image)
            draw.text((index*80+4,row*72+3),f'{name} {index}',fill='#f3c887')
            view=Image.new('RGB',(128,80),'#34434b')
            view.paste(image,(32,16),image)
            ImageDraw.Draw(view).text((3,3),name,fill='#f3c887')
            views.append(view); durations.append(spec[-1])
        assert len({pose(s).tobytes() for s in specs})>=3, name
        request['actions'][name]={'loop':name in ('idle','walk','run'),'frames':entries}
    (ROOT/'actions.json').write_text(json.dumps(request,indent=2)+'\n')
    sheet.save(ROOT/'contact-sheet-1x.png')
    sheet.resize((sheet.width*3,sheet.height*3),Image.Resampling.NEAREST).save(ROOT/'contact-sheet-3x.png')
    views[0].save(ROOT/'preview-1x.gif',save_all=True,append_images=views[1:],duration=durations,loop=0,disposal=2)
    scene={'schema_version':1,'id':'clockwork-beetle','brief':{'title':'Clockwork beetle','goal':'Inspect an original articulated six-action mechanical beetle.','controls':'Read-only scene; action playback is selected by the host.'},'coordinates':{'units':'meters','up':'+Y','handedness':'right'},'assets':[{'id':'beetle','producer':'pixel-action-set','request':'actions.json'}], 'nodes':[{'id':'beetle-actor','asset':'beetle','action':'idle','position':[0,0,0],'rotation_degrees':[0,0,0],'scale':[1,1,1],'size_m':0.64}]}
    (ROOT/'scene.json').write_text(json.dumps(scene,indent=2)+'\n')
    print(f'Authored {sum(len(s) for s in ACTIONS.values())} poses; six actions; contact at attack frame 2.')

if __name__=='__main__': main()
