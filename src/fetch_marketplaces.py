#!/usr/bin/env python3
"""Coleta pedidos do Mercado Livre e Shopee e consolida em CSV para Looker Studio."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

import requests


@dataclass
class MercadoLivreConfig:
    access_token: str
    seller_id: str


@dataclass
class ShopeeConfig:
    partner_id: str
    partner_key: str
    shop_id: str
    access_token: str


class MercadoLivreClient:
    base_url = "https://api.mercadolibre.com"

    def __init__(self, cfg: MercadoLivreConfig) -> None:
        self.cfg = cfg

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.cfg.access_token}"}

    def list_orders(self, date_from: str, date_to: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/orders/search"
        params = {
            "seller": self.cfg.seller_id,
            "order.date_created.from": date_from,
            "order.date_created.to": date_to,
            "sort": "date_desc",
            "limit": 50,
        }

        orders: List[Dict[str, Any]] = []
        offset = 0

        while True:
            params["offset"] = offset
            resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
            batch = payload.get("results", [])
            if not batch:
                break
            orders.extend(batch)
            paging = payload.get("paging", {})
            total = int(paging.get("total", 0))
            offset += int(paging.get("limit", 50))
            if offset >= total:
                break

        return orders

    @staticmethod
    def normalize(order: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "marketplace": "mercado_livre",
            "order_id": order.get("id"),
            "created_at": order.get("date_created"),
            "status": order.get("status"),
            "currency": order.get("currency_id"),
            "total_amount": order.get("total_amount"),
            "shipping_cost": (order.get("shipping") or {}).get("cost"),
            "items_count": len(order.get("order_items") or []),
            "buyer_nickname": ((order.get("buyer") or {}).get("nickname")),
        }


class ShopeeClient:
    base_url = "https://partner.shopeemobile.com"

    def __init__(self, cfg: ShopeeConfig) -> None:
        self.cfg = cfg

    def _timestamp(self) -> int:
        return int(dt.datetime.now(tz=dt.timezone.utc).timestamp())

    def _signature(self, path: str, timestamp: int) -> str:
        base_string = f"{self.cfg.partner_id}{path}{timestamp}{self.cfg.access_token}{self.cfg.shop_id}"
        return hmac.new(
            self.cfg.partner_key.encode("utf-8"),
            base_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _signed_params(self, path: str) -> Dict[str, Any]:
        timestamp = self._timestamp()
        return {
            "partner_id": int(self.cfg.partner_id),
            "timestamp": timestamp,
            "access_token": self.cfg.access_token,
            "shop_id": int(self.cfg.shop_id),
            "sign": self._signature(path, timestamp),
        }

    def list_order_sn(self, date_from_unix: int, date_to_unix: int) -> List[str]:
        # Endpoint e escopo variam por região/versão da API da Shopee.
        path = "/api/v2/order/get_order_list"
        params = {
            **self._signed_params(path),
            "time_range_field": "create_time",
            "time_from": date_from_unix,
            "time_to": date_to_unix,
            "page_size": 50,
            "order_status": "READY_TO_SHIP",
        }
        resp = requests.get(f"{self.base_url}{path}", params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        return [item["order_sn"] for item in payload.get("response", {}).get("order_list", [])]

    def get_order_details(self, order_sns: Iterable[str]) -> List[Dict[str, Any]]:
        order_sns = list(order_sns)
        if not order_sns:
            return []

        path = "/api/v2/order/get_order_detail"
        params = {
            **self._signed_params(path),
            "order_sn_list": ",".join(order_sns),
            "response_optional_fields": "item_list,total_amount,actual_shipping_fee,buyer_user_id,currency",
        }
        resp = requests.get(f"{self.base_url}{path}", params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        return payload.get("response", {}).get("order_list", [])

    @staticmethod
    def normalize(order: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "marketplace": "shopee",
            "order_id": order.get("order_sn"),
            "created_at": dt.datetime.fromtimestamp(
                int(order.get("create_time", 0)), tz=dt.timezone.utc
            ).isoformat(),
            "status": order.get("order_status"),
            "currency": order.get("currency"),
            "total_amount": order.get("total_amount"),
            "shipping_cost": order.get("actual_shipping_fee"),
            "items_count": len(order.get("item_list") or []),
            "buyer_nickname": order.get("buyer_user_id"),
        }


def write_csv(rows: List[Dict[str, Any]], output_path: str) -> None:
    if not rows:
        return

    fields = list(rows[0].keys())
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-from", required=True, help="Data inicial ISO8601, ex: 2026-01-01T00:00:00.000Z")
    parser.add_argument("--date-to", required=True, help="Data final ISO8601, ex: 2026-01-31T23:59:59.999Z")
    parser.add_argument("--output", default="data/orders_consolidado.csv")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    all_rows: List[Dict[str, Any]] = []

    ml_token = os.getenv("ML_ACCESS_TOKEN")
    ml_seller = os.getenv("ML_SELLER_ID")
    if ml_token and ml_seller:
        ml = MercadoLivreClient(MercadoLivreConfig(ml_token, ml_seller))
        ml_orders = ml.list_orders(args.date_from, args.date_to)
        all_rows.extend([ml.normalize(order) for order in ml_orders])

    shopee_partner_id = os.getenv("SHOPEE_PARTNER_ID")
    shopee_partner_key = os.getenv("SHOPEE_PARTNER_KEY")
    shopee_shop_id = os.getenv("SHOPEE_SHOP_ID")
    shopee_access_token = os.getenv("SHOPEE_ACCESS_TOKEN")

    if all([shopee_partner_id, shopee_partner_key, shopee_shop_id, shopee_access_token]):
        shopee = ShopeeClient(
            ShopeeConfig(
                partner_id=shopee_partner_id,
                partner_key=shopee_partner_key,
                shop_id=shopee_shop_id,
                access_token=shopee_access_token,
            )
        )
        time_from = int(dt.datetime.fromisoformat(args.date_from.replace("Z", "+00:00")).timestamp())
        time_to = int(dt.datetime.fromisoformat(args.date_to.replace("Z", "+00:00")).timestamp())

        order_sns = shopee.list_order_sn(time_from, time_to)
        shopee_orders = shopee.get_order_details(order_sns)
        all_rows.extend([shopee.normalize(order) for order in shopee_orders])

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    write_csv(all_rows, args.output)
    print(f"{len(all_rows)} pedidos exportados para {args.output}")


if __name__ == "__main__":
    main()
