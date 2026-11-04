import {chromium} from '@playwright/test';
import {readFileSync,writeFileSync,mkdirSync,copyFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';

const root=resolve(import.meta.dirname,'..');
const generation=JSON.parse(readFileSync(resolve(root,'resources/menu-photos/generation-v1.json')));
const menu=JSON.parse(readFileSync(resolve(root,'resources/menu-transcription.json')));
const slugs={1:'chicken-biryani',2:'mutton-biryani',3:'egg-biryani',4:'plain-biryani',5:'plain-biryani',6:'chilli-chicken',7:'chilli-chicken',8:'chicken-fry',9:'chicken-chukka',10:'pepper-chicken',11:'chicken-lollipop',12:'chicken-manchurian',13:'chicken-mongolian',14:'pepper-chicken-gravy',15:'chicken-gravy',16:'mutton-gravy',17:'kudal-gravy',18:'mutton-fry',19:'mutton-chukka',20:'kudal-fry',21:'grill-chicken',22:'grill-chicken',23:'grill-chicken',24:'pepper-grill-chicken',25:'pepper-grill-chicken',26:'pepper-grill-chicken',27:'egg-poriyal',28:'boiled-egg',29:'chicken-biryani',30:'chicken-biryani',31:'mutton-biryani',32:'mutton-biryani',33:'egg-biryani',34:'egg-biryani',35:'plain-biryani',36:'plain-biryani'};
const browser=await chromium.launch({headless:true});
const page=await browser.newPage();
const assets=[];
try {
  for(const asset of generation.images) {
    const original=resolve(root,asset.original_in_workspace), thumbnail=resolve(root,asset.thumbnail);
    mkdirSync(resolve(original,'..'),{recursive:true});
    mkdirSync(resolve(thumbnail,'..'),{recursive:true});
    // Preserve selected generator output in the project; never delete its original.
    if(!existsSync(original)) copyFileSync(asset.source,original);
    const encoded=await page.evaluate(async(data)=>{
      const image=await createImageBitmap(await (await fetch(data)).blob());
      const scale=Math.min(1,384/Math.max(image.width,image.height));
      const canvas=new OffscreenCanvas(Math.round(image.width*scale),Math.round(image.height*scale));
      const context=canvas.getContext('2d');
      context.drawImage(image,0,0,canvas.width,canvas.height); image.close();
      let blob=await canvas.convertToBlob({type:'image/jpeg',quality:0.78});
      if(blob.size>49152) blob=await canvas.convertToBlob({type:'image/jpeg',quality:0.68});
      const reader=new FileReader();
      const dataURL=await new Promise((resolve,reject)=>{reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(reader.error);reader.readAsDataURL(blob);});
      return {dataURL,width:canvas.width,height:canvas.height};
    },`data:image/png;base64,${readFileSync(original).toString('base64')}`);
    const bytes=Buffer.from(encoded.dataURL.split(',')[1],'base64');
    if(bytes.length>49152) throw new Error(`Thumbnail too large: ${asset.slug}`);
    if(!existsSync(thumbnail)) writeFileSync(thumbnail,bytes);
    else if(!readFileSync(thumbnail).equals(bytes)) throw new Error(`Refusing to overwrite different image: ${thumbnail}`);
    assets.push({slug:asset.slug,src:`./menu-photos/v1/${asset.slug}.jpg`,width:encoded.width,height:encoded.height,bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex'),products:menu.items.filter(item=>slugs[Number(item.reference_id.slice(5))]===asset.slug).map(item=>({id:item.reference_id,name:item.source_label,portion:item.portion_label}))});
  }
  const result={version:'v1',illustrative:true,assets};
  writeFileSync(resolve(root,'restaurant/menu-photos.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify({photos:assets.length,products:assets.flatMap(a=>a.products).length,total_bytes:assets.reduce((sum,a)=>sum+a.bytes,0),max_photo_bytes:Math.max(...assets.map(a=>a.bytes)),max_edge:Math.max(...assets.flatMap(a=>[a.width,a.height]))}));
} finally {await browser.close();}
