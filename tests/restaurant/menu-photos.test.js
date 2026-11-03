import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {installMenuPhotos, MENU_PHOTO_KEY} from "../../restaurant/menu-photo-install.js";
import {createBackup, restoreBackup} from "../../restaurant/backup.js";
import {setup, database, MemoryImages, order} from "./helpers.js";
const manifest=JSON.parse(readFileSync(new URL('../../restaurant/menu-photos.json',import.meta.url)));
const readPhoto=async asset=>`data:image/jpeg;base64,${readFileSync(new URL(`../../restaurant/public/${asset.src.slice(2)}`,import.meta.url)).toString('base64')}`;

test('MENU-PHOTO-01 one-time photos preserve uploaded/renamed products, prices and saved sales',async()=>{
  const {ledger,db}=await setup(), images=new MemoryImages();
  try {
    const custom=await images.put('data:image/jpeg;base64,AQID');
    let products=await ledger.products();
    await ledger.saveProduct({...products.find(p=>p.id==='menu-001'),image:custom});
    await ledger.saveProduct({...products.find(p=>p.id==='menu-002'),name:'Owner changed this dish'});
    await ledger.saveProduct({...products.find(p=>p.id==='menu-003'),active:0});
    const sale=await ledger.checkout(order()), saved=await ledger.sale(sale.id);
    products=await ledger.products();
    assert.equal(await installMenuPhotos({ledger,images,manifest,readPhoto}),34);
    const after=await ledger.products();
    for(const product of products) {
      const updated=after.find(p=>p.id===product.id);
      assert.deepEqual({...updated,image:product.image},product);
    }
    assert.equal(after.find(p=>p.id==='menu-001').image,custom);
    assert.equal(after.find(p=>p.id==='menu-002').image,null);
    assert.equal(after.find(p=>p.id==='menu-003').active,0);
    assert.deepEqual(await ledger.sale(sale.id),saved);
    const removed=after.find(p=>p.id==='menu-004');
    await ledger.saveProduct({...removed,image:null});
    assert.equal(await installMenuPhotos({ledger,images,manifest,readPhoto:()=>assert.fail('Warm start must not reload bundled photos')}),0);
    assert.equal((await ledger.products()).find(p=>p.id===removed.id).image,null);
  } finally {await db.close();}
});

test('MENU-PHOTO-02 interrupted file preparation keeps the active menu untouched and retries safely',async()=>{
  const {ledger,db}=await setup(), images=new MemoryImages();
  try {
    const before=await ledger.snapshot(); let reads=0;
    await assert.rejects(installMenuPhotos({ledger,images,manifest,readPhoto:async asset=>{
      if(++reads===3) throw new Error('Storage interrupted');
      return readPhoto(asset);
    }}),/Storage interrupted/);
    assert.deepEqual(await ledger.snapshot(),before);
    assert.equal(await ledger.localSetting(MENU_PHOTO_KEY),null);
    assert.equal(await installMenuPhotos({ledger,images,manifest,readPhoto}),36);
    assert.equal(new Set((await ledger.products()).map(p=>p.image)).size,22);
  } finally {await db.close();}
});

test('MENU-PHOTO-03 product references and install marker roll back together on database failure',async()=>{
  const {ledger,db}=await setup(), images=new MemoryImages();
  try {
    const before=await ledger.snapshot(), run=db.run;
    db.run=async(sql,args)=>{
      if(sql.startsWith('INSERT INTO drafts')) throw new Error('Commit preparation failed');
      return run(sql,args);
    };
    await assert.rejects(installMenuPhotos({ledger,images,manifest,readPhoto}),/Commit preparation failed/);
    db.run=run;
    assert.deepEqual(await ledger.snapshot(),before);
    assert.equal(await ledger.localSetting(MENU_PHOTO_KEY),null);
  } finally {await db.close();}
});

test('MENU-PHOTO-04 an owner upload made during preparation wins the final transaction recheck',async()=>{
  const {ledger,db}=await setup(), images=new MemoryImages();
  try {
    const custom=await images.put('data:image/jpeg;base64,BAUG');
    assert.equal(await installMenuPhotos({ledger,images,manifest,readPhoto:async asset=>{
      if(asset.slug==='chicken-biryani') {
        const current=(await ledger.products()).find(p=>p.id==='menu-001');
        await ledger.saveProduct({...current,image:custom});
      }
      return readPhoto(asset);
    }}),35);
    assert.equal((await ledger.products()).find(p=>p.id==='menu-001').image,custom);
  } finally {await db.close();}
});

test('MENU-PHOTO-05 complete backup restores photos and the removal-preserving install marker',async()=>{
  const first=await setup(), second=await setup(), images=new MemoryImages(), restored=new MemoryImages();
  try {
    await installMenuPhotos({ledger:first.ledger,images,manifest,readPhoto});
    await first.ledger.checkout(order());
    const source=await createBackup(first.ledger,images);
    await restoreBackup(source,second.ledger,restored,()=>database());
    assert.deepEqual(await second.ledger.snapshot(),await first.ledger.snapshot());
    for(const product of await second.ledger.products()) assert.equal(await restored.read(product.image),await images.read(product.image));
    assert.equal(await installMenuPhotos({ledger:second.ledger,images:restored,manifest,readPhoto:()=>assert.fail('Restored markers must skip installation')}),0);
  } finally {await first.db.close();await second.db.close();}
});
