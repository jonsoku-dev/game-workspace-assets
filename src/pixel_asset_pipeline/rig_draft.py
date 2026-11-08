"""Conservative six-part proposals for separated, frontal neutral humanoid sprites."""
import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw

from . import motion
from .action_set import local_path
from .bundle import open_png, write_json

PARTS = ('torso', 'head', 'arm_left', 'arm_right', 'leg_left', 'leg_right')
COLORS = ('#f5c65e', '#85c9ff', '#fd8e92', '#b8a0fa', '#8ad39f', '#6fd6dc')


def runs(xs):
    result = []
    for x in sorted(xs):
        if result and result[-1][1] == x:
            result[-1][1] += 1
        else:
            result.append([x, x+1])
    return result


def connected(pixels):
    pending, seen = [min(pixels)], set()
    while pending:
        xy = pending.pop()
        if xy in seen:
            continue
        seen.add(xy)
        x, y = xy
        pending.extend(p for p in ((x-1,y), (x+1,y), (x,y-1), (x,y+1)) if p in pixels and p not in seen)
    return seen == pixels


def fail(reason):
    raise ValueError('unsupported or uncertain frontal neutral silhouette: ' + reason + '; author an explicit motion rig')


def analyse(master, guides):
    opaque = {(x,y) for y in range(master.height) for x in range(master.width) if master.getpixel((x,y))[3]}
    if not opaque or not connected(opaque):
        fail('figure must be one connected component without detached effects or equipment')
    left, right = min(x for x,y in opaque), max(x for x,y in opaque)+1
    top, bottom = min(y for x,y in opaque), max(y for x,y in opaque)+1
    if left == 0 or top == 0 or right == master.width or bottom == master.height or bottom-top < 12:
        fail('figure needs transparent margins and at least 12 occupied rows')
    mirrored = {(left+right-1-x,y) for x,y in opaque}
    symmetry = len(opaque & mirrored)/len(opaque | mirrored)
    if symmetry < .85:
        fail('silhouette is not sufficiently bilateral for a frontal proposal')
    rows = {y:runs(x for x, yy in opaque if yy == y) for y in range(top,bottom)}
    if any(not row for row in rows.values()):
        fail('blank rows disconnect the figure')
    split = bottom
    while split > top and len(rows[split-1]) == 2:
        split -= 1
    if bottom-split < 3:
        fail('two separate legs must be visible in at least three bottom rows')
    arm_rows = [y for y in range(top,split) if len(rows[y]) == 3]
    if len(arm_rows) < 3 or arm_rows != list(range(arm_rows[0],arm_rows[-1]+1)):
        fail('both arms must be separated from the torso for one continuous band of at least three rows')
    first, last = arm_rows[0], arm_rows[-1]
    body_left = min(rows[y][1][0] for y in arm_rows)
    body_right = max(rows[y][1][1] for y in arm_rows)
    center = (body_left+body_right-1)//2
    if not all(rows[y][1][0] <= center < rows[y][1][1] for y in arm_rows):
        fail('middle arm-band run does not identify a stable central torso')
    if any(len(rows[y]) != 1 for y in range(top,first)) or any(len(rows[y]) != 1 for y in range(last+1,split)):
        fail('head/shoulder/waist contains additional uncertain splits')
    for y in range(split,bottom):
        a,b = rows[y]
        if a[1] > center+1 or b[0] <= center or a[1] >= b[0]:
            fail('separated legs must remain on opposite sides of the torso')
    shoulder = first
    while shoulder > top:
        band = rows[shoulder-1][0]
        if band[0] < body_left and band[1] > body_right:
            shoulder -= 1
        else:
            break
    if shoulder == first:
        fail('no connected shoulder bridge above the separated arms')
    if not top+2 < shoulder < split:
        fail('head and shoulder bands cannot be distinguished')
    widths = {y: rows[y][0][1]-rows[y][0][0] for y in range(top+2,shoulder)}
    neck_candidates = [y for y,w in widths.items() if w == min(widths.values())]
    if 'neck_y' in guides:
        neck = guides['neck_y']
        if neck not in widths:
            fail('neck_y must be between head top and shoulder bridge')
    else:
        neck = neck_candidates[0]
        head_width = max(rows[y][0][1]-rows[y][0][0] for y in range(top,neck+1))
        if (neck_candidates != list(range(neck,neck_candidates[-1]+1))
                or min(widths.values()) > min(head_width-2, body_right-body_left-2)):
            fail('no unique neck constriction; supply a reviewed neck_y guide or an explicit rig')
    if 'shoulder_y' in guides:
        if not shoulder <= guides['shoulder_y'] < first:
            fail('shoulder_y must lie in the observed connected shoulder bridge')
        shoulder = guides['shoulder_y']
    hip = guides.get('hip_y', split)
    if not last < hip <= split:
        fail('hip_y must lie below the arms and at or above the observed leg split')
    if not top+2 <= neck < shoulder < hip < bottom-2:
        fail('head/shoulder/hip guides are out of order')
    assigned = {name:set() for name in PARTS}
    for x,y in opaque:
        if y < neck:
            name = 'head'
        elif y >= hip:
            name = 'leg_left' if x <= center else 'leg_right'
        elif y >= shoulder and y <= last:
            if y < first:
                name = 'arm_left' if x < body_left else 'arm_right' if x >= body_right else 'torso'
            else:
                row = rows[y]
                name = 'arm_left' if x < row[0][1] else 'arm_right' if x >= row[2][0] else 'torso'
        else:
            name = 'torso'
        assigned[name].add((x,y))
    if any(len(pixels) < 4 or not connected(pixels) for pixels in assigned.values()):
        fail('each proposed body part must have at least four connected pixels')
    return assigned, {'neck_y':neck, 'shoulder_y':shoulder, 'hip_y':hip}, {
        'bbox_xywh':[left,top,right-left,bottom-top], 'bilateral_iou':round(symmetry,6),
        'arm_separation_rows':[first,last], 'leg_separation_y':split,
        'torso_span_x':[body_left,body_right], 'center_x':center}


def preview(master, parts, stage):
    scale = min(8, 512//max(master.size))
    sw, sh = master.width*scale, master.height*scale
    x0, x1, y0 = master.width+32, master.width+sw+56, 48
    image = Image.new('RGB', (x1+sw+24, max(sh+90, 250)), '#24313d')
    draw = ImageDraw.Draw(image)
    draw.text((12,12),'MASTER 1x',fill='white')
    draw.text((x0,12),f'JOINT DRAFT {scale}x',fill='white')
    draw.text((x1,12),'MASK PARTITION / REVIEW REQUIRED',fill='white')
    image.paste(master,(12,y0),master)
    enlarged = master.resize((sw,sh),Image.Resampling.NEAREST)
    image.paste(enlarged,(x0,y0),enlarged)
    colored = Image.new('RGBA',master.size)
    for i,part in enumerate(parts):
        ink = ImageDraw.Draw(colored)
        for xy in part['pixels']:
            ink.point(xy,fill=COLORS[i])
    enlarged = colored.resize((sw,sh),Image.Resampling.NEAREST)
    image.paste(enlarged,(x1,y0),enlarged)
    anchors = {p['id']:(x0+p['anchor_px'][0]*scale,y0+p['anchor_px'][1]*scale) for p in parts}
    for i,part in enumerate(parts):
        if part['parent']:
            draw.line((anchors[part['parent']],anchors[part['id']]),fill='white',width=1)
        x,y=anchors[part['id']]
        draw.ellipse((x-3,y-3,x+3,y+3),fill=COLORS[i],outline='white')
        draw.text((x+5,y-8),str(i+1),fill='white')
        draw.text((12+i*(image.width//6),image.height-35),f"{i+1} {part['id']}",fill=COLORS[i])
    draw.text((12,image.height-18),'Proposed joints only; inspect anatomy and masks before approval. No hidden pixels generated.',fill='white')
    image.save(stage/'joint-preview.png')


def produce(request_path: Path, stage: Path):
    snapshots = {}
    request_bytes = motion.snapshot(request_path,1_048_576,'rig-draft request',snapshots)
    request = json.loads(request_bytes)
    if (not isinstance(request,dict) or type(request.get('schema_version')) is not int
            or request['schema_version'] != 1 or set(request)-{'schema_version','source','guides'}):
        raise ValueError('rig-draft requires schema_version 1, source and optional guides')
    guides = request.get('guides',{})
    if (not isinstance(guides,dict) or set(guides)-{'neck_y','shoulder_y','hip_y'}
            or any(type(v) is not int for v in guides.values())):
        raise ValueError('guides supports integer neck_y, shoulder_y, hip_y only')
    source = local_path(request_path.parent,request.get('source'))
    source_bytes = motion.snapshot(source,16_777_216,'source',snapshots)
    master = open_png(io.BytesIO(source_bytes),max_pixels=128**2).convert('RGBA')
    if min(master.size) < 16 or max(master.size) > 128:
        raise ValueError('rig-draft native PNG dimensions must be 16..128')
    if set(motion.pixel_data(master.getchannel('A'))) != {0,255}:
        raise ValueError('rig-draft requires transparent and opaque pixels with binary alpha; snap soft sources first')
    master.putdata([p if p[3] else (0,0,0,0) for p in motion.pixel_data(master)])
    assigned, inferred, geometry = analyse(master,guides)
    center, hip = geometry['center_x'], inferred['hip_y']
    body_left,body_right = geometry['torso_span_x']
    anchors = {'torso':[center,hip], 'head':[center,inferred['neck_y']],
               'arm_left':[body_left-1,inferred['shoulder_y']],
               'arm_right':[body_right,inferred['shoulder_y']]}
    for side in ('left','right'):
        pixels = assigned['leg_'+side]
        first_y = min(y for x,y in pixels)
        xs = [x for x,y in pixels if y == first_y]
        anchors['leg_'+side] = [(min(xs)+max(xs))//2,first_y]
    files = {'master':'master.png','request':'rig-draft.request.json','preview':'joint-preview.png',
             'neutral':'neutral.png','inspection':'inspection.json'}
    parts = []
    for name in PARTS:
        filename = name+'-mask.png'
        mask = Image.new('L',master.size)
        for xy in assigned[name]:
            mask.putpixel(xy,255)
        mask.save(stage/filename)
        files[name+'_mask'] = filename
        part = {'id':name,'role':name,'parent':None if name == 'torso' else 'torso',
                'anchor_px':anchors[name],'mask':filename}
        if name.startswith('leg_'):
            foot_y = max(y for x,y in assigned[name])
            xs = [x for x,y in assigned[name] if y == foot_y]
            part['contact_px'] = [(min(xs)+max(xs))//2,foot_y]
        parts.append(part)
    draft = {'schema_version':1,'master':'master.png','approved':False,
             'pivot_px_from_top_left':[center,geometry['bbox_xywh'][1]+geometry['bbox_xywh'][3]],
             'rig':{'parts':parts}}
    (stage/'master.png').write_bytes(source_bytes)
    validated = motion.load_rig(draft,stage,master)
    neutral,_ = motion.render(master,validated,{'parts':{},'root_offset_px':[0,0]})
    if neutral.tobytes() != master.tobytes():
        raise ValueError('rig-draft neutral reconstruction differs from captured master')
    neutral.save(stage/'neutral.png')
    write_json(stage/'rig-draft.request.json',draft)
    preview(master,validated,stage)
    write_json(stage/'inspection.json',{
        'schema_version':1,'status':'draft','approved':False,'visual_review':'required',
        'artistic_acceptance':'unverified','anatomical_review':'required',
        'source':{'path':request['source'],'sha256':hashlib.sha256(source_bytes).hexdigest(),
                  'request_sha256':hashlib.sha256(request_bytes).hexdigest(),'size_px':list(master.size)},
        'method':'restricted-frontal-row-separation-six-part-proposal',
        'supplied_guides':guides,'proposed_guides':inferred,'geometry':geometry,
        'exact_partition':True,'neutral_exact_visible_reconstruction':True,
        'parts':[{'id':p['id'],'pixel_count':len(p['pixels']),'anchor_px':p['anchor_px'],
                  'mask_sha256':hashlib.sha256((stage/p['mask']).read_bytes()).hexdigest()} for p in validated],
        'limitations':['Six visible cutout parts only; no 17-bone rig or automatic approval.',
                      'Image-left/image-right labels are not anatomical handedness.',
                      'Bilateral silhouette and row gaps do not prove anatomy; inspect every proposed mask and joint.',
                      'No hidden anatomy, equipment extraction, or replacement pixels are generated.',
                      'Edit masks/joints and explicitly review the master before changing approved:false.']})
    return files
