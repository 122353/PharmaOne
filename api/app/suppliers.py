"""Synthetic supply-chain links limited to the owning pharmacy."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import current_user
from .db import get_db
from .models import InventoryItem, Match, Pharmacy, SupplierLink

router=APIRouter()


def pharmacy_for(db: Session, user: str) -> Pharmacy:
    pharmacy=db.scalar(select(Pharmacy).where(Pharmacy.owner_id==user))
    if not pharmacy:raise HTTPException(404,"Create your pharmacy profile first")
    return pharmacy


class LinkInput(BaseModel):
    inventory_id: str
    supplier: str=Field(min_length=2,max_length=160)
    distributor: str=Field(min_length=2,max_length=160)


@router.post('/api/suppliers/links')
def save_link(data:LinkInput,user:str=Depends(current_user),db:Session=Depends(get_db)):
    pharmacy=pharmacy_for(db,user)
    item=db.scalar(select(InventoryItem).where(InventoryItem.id==data.inventory_id,InventoryItem.pharmacy_id==pharmacy.id))
    if not item:raise HTTPException(404,"Inventory item not found")
    link=db.scalar(select(SupplierLink).where(SupplierLink.inventory_id==item.id,SupplierLink.pharmacy_id==pharmacy.id))
    if not link:link=SupplierLink(pharmacy_id=pharmacy.id,inventory_id=item.id)
    link.supplier=data.supplier
    link.distributor=data.distributor
    db.add(link)
    db.commit()
    return {"id":link.id,"synthetic":True}


@router.get('/api/suppliers/exposure')
def exposure(user:str=Depends(current_user),db:Session=Depends(get_db)):
    pharmacy=pharmacy_for(db,user)
    rows=[]
    for link in db.scalars(select(SupplierLink).where(SupplierLink.pharmacy_id==pharmacy.id)):
        item=db.scalar(select(InventoryItem).where(InventoryItem.id==link.inventory_id,InventoryItem.pharmacy_id==pharmacy.id))
        if not item:continue
        affected=db.scalar(select(Match.id).where(Match.pharmacy_id==pharmacy.id,Match.inventory_id==item.id,Match.status!='no_identified_match').limit(1))
        rows.append({"id":link.id,"manufacturer":item.manufacturer,"distributor":link.distributor,
                     "supplier":link.supplier,"pharmacy":pharmacy.name,"medicine":item.medicine_name,
                     "batch_number":item.batch_number,"inventory_id":item.id,
                     "potential_exposure":bool(affected),"synthetic":True})
    return rows
