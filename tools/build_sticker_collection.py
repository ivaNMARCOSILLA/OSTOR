"""Slice eleven generated emoji sheets into 999 distinct costume assets.

Usage: python tools/build_sticker_collection.py --sources /private/sheets.json
The JSON maps each series slug to a local source PNG; sources are never bundled.
"""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image,ImageChops,ImageFilter

ROOT=Path(__file__).resolve().parents[1]
SERIES=[('cosmos','Espacio','Órbita alegre'),('fantasia','Fantasía','Magia con encanto'),('oficios','Profesiones','Talento en acción'),('aventura','Aventuras','Espíritu aventurero'),('musica','Música','Ritmo y emoción'),('deporte','Deporte','Equipo con energía'),('animales','Animales','Disfraz animal'),('estaciones','Estaciones','Un día especial'),('fiesta','Fiesta','Momento de fiesta'),('sabores','Sabores y viajes','Sabor viajero'),('leyendas','Leyendas de Ol','Leyenda de Ol')]
LEGACY=[('spark',1),('wave',5),('heart',15),('star',30),('planet',60),('leaf',120),('compass',240),('moon',480),('bolt',960),('infinity',1440),('crown',2880)]


LAYOUTS={
 'cosmos':([84,212,327,459,580,702,836,966,1088,1193],[69,185,308,430,555,679,807,937,1062,1186],10),
 'fantasia':([71,210,330,456,591,726,844,969,1092,1201],[71,196,319,444,564,688,815,942,1066,1188],10),
 'oficios':([68,162,258,358,460,566,662,757,859,956,1055,1174],[78,199,319,440,558,680,804,927,1050,1173],11),
 'aventura':([59,175,300,433,558,690,807,942,1062,1184],[69,192,312,437,563,690,814,938,1064,1187],10),
 'musica':([68,195,308,438,563,684,813,938,1066,1185],[67,183,317,437,561,685,811,942,1060,1186],10),
 'deporte':([60,163,266,370,480,582,698,809,924,1042,1124,1200],[63,197,314,440,570,688,822,948,1068,1194],10),
 'animales':([88,198,315,435,571,695,822,941,1058,1196],[62,181,302,418,532,651,774,892,1010],10),
 'estaciones':([63,175,285,411,539,693,838,973,1090,1211],[68,192,318,438,562,688,822,944,1069,1185],10),
 'fiesta':([101,240,382,522,666,808,948,1090,1206],[73,199,324,457,573,697,820,946,1064,1194],9),
 'sabores':([86,208,329,460,592,705,806,928,1030,1128,1223],[69,194,317,445,569,690,814,938,1062,1188],10),
 'leyendas':([74,204,332,465,595,722,854,988,1120],[63,184,313,440,563,690,821,956,1060,1194],9)}
COUNTS={slug:(92 if slug=='oficios' else 90 if slug in {'animales','fiesta','leyendas'} else 91) for slug,_,_ in SERIES}


def source_cell(slug,position):
    rows,columns,eligible=LAYOUTS[slug];total=eligible*len(columns)
    return round(position*(total-1)/(COUNTS[slug]-1))


def bounds(centers,index,limit):
    start=0 if index==0 else round((centers[index-1]+centers[index])/2)
    stop=min(limit,round(centers[index]+(centers[index]-centers[index-1])/2)) if index==len(centers)-1 else round((centers[index]+centers[index+1])/2)
    return max(0,start-13),min(limit,stop+13)


ROW_LABELS={
 'cosmos':['Astronauta','Visitante extraterrestre','Piloto espacial','Robot simpático','Explorador lunar','Planeta viajero','Corona estelar','Cometa veloz','Aviador del cosmos','Cohete alegre'],
 'animales':['Gato disfrazado','Zorro travieso','Panda simpático','Rana alegre','Tiburón amable','Patito curioso','Abeja risueña','Búho sabio','Tigre divertido','Conejo curioso'],
 'oficios':['Cocinero alegre','Bombero valiente','Sanitario amable','Médico amable','Científico curioso','Constructor alegre','Artista con color','Jardinero sonriente','Fotógrafo creativo','Profesor alegre','Cartero viajero','Pastelero dulce'],
 'aventura':['Pirata simpático','Marinero alegre','Vaquero aventurero','Explorador curioso'],
 'deporte':['Futbolista sonriente','Equipo de baloncesto','Tenista divertido']}


def record(counter,slug,title,prefix,position):
    cell=source_cell(slug,position);row=cell//len(LAYOUTS[slug][1]);labels=ROW_LABELS.get(slug,[]);label=labels[row] if row<len(labels) else prefix
    ident,minutes=LEGACY[counter-1] if counter<=11 else (f'emoji_{counter:04}',(counter-11)*3)
    return dict(id=ident,name=f'{label} {position+1:03}',minutes=minutes,points=minutes*10,image=f'/assets/stickers/costumes/{slug}-{position+1:03}.webp',series=title,source_cell=cell)


def records_only():
    records=[];packs=[];counter=0
    for index,(slug,title,prefix) in enumerate(SERIES):
        count=COUNTS[slug]
        for position in range(count):
            counter+=1;records.append(record(counter,slug,title,prefix,position))
        packs.append(dict(id=slug,name=title,count=count,image=f'/assets/stickers/sheets/{slug}.webp'))
    return records,packs


def write_metadata(records,packs):
    folder=ROOT/'assets'/'stickers'
    for target,value in [(folder/'catalogue.json',records),(folder/'sheets'/'index.json',packs)]:
        temporary=target.with_suffix('.json.tmp');temporary.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n');temporary.replace(target)


def normalize_cell(cell):
    # Recover the complete central sticker from a slightly overlapping crop.
    # Erosion breaks faint alpha bridges; dilation restores its clean outline.
    alpha=cell.getchannel('A');binary=alpha.point(lambda value:255 if value>128 else 0).filter(ImageFilter.MinFilter(3))
    width,height=cell.size;pixels=bytearray(binary.tobytes());center=(height//2)*width+width//2
    if not pixels[center]:
        candidates=[i for i,value in enumerate(pixels) if value and abs(i%width-width//2)<width//4 and abs(i//width-height//2)<height//4]
        if not candidates:raise ValueError('Empty central sticker')
        center=min(candidates,key=lambda i:(i%width-width//2)**2+(i//width-height//2)**2)
    component=bytearray(len(pixels));pending=[center];pixels[center]=0
    while pending:
        point=pending.pop();component[point]=255;x=point%width
        for neighbor in ((point-1 if x else -1),(point+1 if x+1<width else -1),point-width,point+width):
            if 0<=neighbor<len(pixels) and pixels[neighbor]:pixels[neighbor]=0;pending.append(neighbor)
    mask=Image.frombytes('L',cell.size,bytes(component)).filter(ImageFilter.MaxFilter(9))
    cell.putalpha(ImageChops.multiply(alpha,mask));bounds=cell.getbbox()
    if not bounds:raise ValueError('Empty sticker cell')
    cell=cell.crop(bounds)
    if cell.width<40 or cell.height<40:raise ValueError('Sticker artwork too small')
    cell.thumbnail((136,136),Image.Resampling.LANCZOS)
    result=Image.new('RGBA',(160,160));result.alpha_composite(cell,((160-cell.width)//2,(160-cell.height)//2))
    return result


def build(sources,partial=False):
    folder=ROOT/'assets'/'stickers';(folder/'costumes').mkdir(exist_ok=True);(folder/'sheets').mkdir(exist_ok=True)
    catalogue=[];packs=[];seen=set();counter=0
    for index,(slug,title,prefix) in enumerate(SERIES):
        count=COUNTS[slug]
        if slug not in sources:
            if partial:counter+=count;continue
            raise ValueError('Missing source sheet: '+slug)
        source=Image.open(sources[slug]).convert('RGBA')
        if min(source.size)<1000 or abs(source.width-source.height)>20:raise ValueError('Expected high-resolution square sheet')
        meta_path=folder/'sheets'/(slug+'.meta.json');source_hash=hashlib.sha256(Path(sources[slug]).read_bytes()).hexdigest();metadata={'source_sha256':source_hash,'algorithm':'central-alpha-v3-grid','count':count,'layout':list(LAYOUTS[slug])}
        reuse=meta_path.exists() and json.loads(meta_path.read_text())==metadata and all((folder/'costumes'/f'{slug}-{i+1:03}.webp').exists() for i in range(count))
        if not (folder/'sheets'/(slug+'.webp')).exists():
            preview=source.copy();preview.thumbnail((1254,1254));preview.save(folder/'sheets'/(slug+'.webp'),format='WEBP',quality=86,method=6)
        for position in range(count):
            row,column=divmod(source_cell(slug,position),len(LAYOUTS[slug][1]));counter+=1;filename=f'{slug}-{position+1:03}.webp'
            if not reuse:
                ys,xs,_=LAYOUTS[slug];left,right=bounds(xs,column,source.width);top,bottom=bounds(ys,row,source.height)
                crop=source.crop((left,top,right,bottom))
                image=normalize_cell(crop);image.save(folder/'costumes'/filename,format='WEBP',quality=90,method=6)
            with Image.open(folder/'costumes'/filename) as final:digest=hashlib.sha256(final.convert('RGBA').tobytes()).hexdigest()
            if digest in seen:raise ValueError('Duplicate sticker image')
            seen.add(digest)
            catalogue.append(record(counter,slug,title,prefix,position))
        meta_path.write_text(json.dumps(metadata,sort_keys=True)+'\n')
        print(json.dumps({'series':slug,'stickers':count,'reused':reuse}),flush=True)
        packs.append(dict(id=slug,name=title,count=count,image='/assets/stickers/sheets/'+slug+'.webp'))
    if not partial:
        assert len(catalogue)==999 and len({item['id'] for item in catalogue})==999
        write_metadata(catalogue,packs)
    return {'stickers':len(catalogue),'sheets':len(packs),'includes_creator':not partial}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--sources',type=Path,required=True);parser.add_argument('--partial',action='store_true');parser.add_argument('--metadata-only',action='store_true');args=parser.parse_args()
    if args.metadata_only:
        write_metadata(*records_only());print('Metadata prepared; artwork is checked by the full build.');raise SystemExit(0)
    print(json.dumps(build(json.loads(args.sources.read_text()),args.partial)))
