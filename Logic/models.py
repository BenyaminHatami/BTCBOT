from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from django.core.cache import cache
from django.db import models, transaction
import requests
import time
import hmac
import base64

from django.db.models import Value
from django.db.models.functions import Concat

from .tasks import monitoring_sltp_orders
from .utils import get_param, interpret_response


class Coin(Enum):
    type = str
    btc_spot = "BTCUSDT_SPBL"
    btc_futures = "BTCUSDT_UMCBL"

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]


class PositionDirection(Enum):
    type = str
    long = "long"
    short = "short"

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]


class SideFutures(Enum):
    type = str
    open_long = "open_long"
    close_long = "close_long"
    open_short = "open_short"
    close_short = "close_short"
    unknown = "unknown"

    @staticmethod
    def get_position_direction(side):
        if side == SideFutures.open_long.value:
            return PositionDirection.long.value
        elif side == SideFutures.open_short.value:
            return PositionDirection.short.value

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]


class PlanType(Enum):
    type = str
    tp = "profit_plan"
    sl = "loss_plan"

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]


class State(Enum):
    type = int
    Active = 1
    Inactive = 2
    Pending = 3

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]


class BaseModel(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    trace = models.TextField(null=True, blank=True, default="")

    class Meta:
        abstract = True

    def add_comment(self, comment):
        self.__class__.objects.filter(id=self.id).update(
            trace=Concat('trace', Value(f'{comment}\n')),
            updated=datetime.now(tz=timezone.utc))


def write_at_cache(id, message, comment):
    cache.set(id, message)
    print(comment)


def read_from_cache(id, comment):
    try:
        read = cache.get(id)
        print(f"{comment}\nRead {read} from cache.")
        return read
    except Exception as e:
        print(f"Got exception in reading from cache: {str(e)}")
        return None


class Trader(BaseModel):
    name = models.CharField(max_length=100)
    api_key = models.CharField(max_length=100)
    secret_key = models.CharField(max_length=100)
    api_passphrase = models.CharField(max_length=100)
    pnl = models.DecimalField(max_digits=10, decimal_places=5, default=0, null=True, blank=True)

    class Meta:
        unique_together = (('name',),)

    def __str__(self):
        return self.name

    def sign(self, message, secret_key):
        mac = hmac.new(bytes(secret_key, encoding='utf8'), bytes(message, encoding='utf-8'), digestmod='sha256')
        d = mac.digest()
        return base64.b64encode(d)

    def pre_hash(self, timestamp, method, request_path, body=None, query_string=None):
        if query_string is None:
            return str(timestamp) + str.upper(method) + request_path + body
        else:
            return str(timestamp) + str.upper(method) + request_path + "?" + query_string

    def create_signature(self, timestamp, method, request_path, body=None, query_string=None):
        message = self.pre_hash(timestamp=str(timestamp), method=method, request_path=request_path, body=body,
                                query_string=query_string)
        signature_b64 = self.sign(message, self.secret_key)
        return signature_b64

    def create_header(self, method, request_path, body=None, query_string=None):
        timestamp = int(time.time_ns() / 1000000)
        signature_b64 = self.create_signature(timestamp=str(timestamp),
                                              method=method,
                                              request_path=request_path,
                                              body=body,
                                              query_string=query_string)
        headers = {
            'ACCESS-KEY': self.api_key,
            'ACCESS-SIGN': signature_b64,
            'ACCESS-TIMESTAMP': str(timestamp),
            'ACCESS-PASSPHRASE': self.api_passphrase,
            'Content-Type': 'application/json',
            'locale': 'en-US'
        }
        return headers

    # def spot_trade(self, quantity: Decimal, side: Side, price: Decimal, coin: Coin):
    #     method = "POST"
    #     request_path = "/api/spot/v1/trade/orders"
    #     body = (f'{{"side":"{side}",'
    #             f'"symbol":"{coin.value}",'
    #             f'"orderType":"limit",'
    #             f'"force":"normal",'
    #             f'"price":"{price}",'
    #             f'"quantity":"{quantity}"}}')
    #
    #     headers = self.create_header(method=method, request_path=request_path, body=body)
    #     response = requests.post(url="https://api.coincatch.com/api/spot/v1/trade/orders",
    #                              data=body,
    #                              headers=headers)
    #     print(response.text)
    #     return response

    def futures_trade(self, coin: Coin.type, quantity: Decimal, side: SideFutures.type):
        method = "POST"
        request_path = "/api/mix/v1/order/placeOrder"
        body = (f'{{"side":"{side}",'
                f'"symbol":"{coin}",'
                f'"orderType":"market",'
                f'"marginCoin":"USDT",'
                f'"size":"{quantity}"}}')

        headers = self.create_header(method=method, request_path=request_path, body=body)
        response = requests.post(url="https://api.coincatch.com/api/mix/v1/order/placeOrder",
                                 data=body,
                                 headers=headers)
        remote_id = interpret_response(response.json(), "orderId")
        print(response.text)
        print(type(remote_id))
        print(f"remote_id is {remote_id} for {self.name} right after futures_trade")
        return remote_id

    def futures_trade_limit(self, coin: Coin.type, quantity: Decimal, side: SideFutures.type, price: Decimal = None):
        method = "POST"
        request_path = "/api/mix/v1/order/placeOrder"
        number_of_tries = 3
        try:
            for _ in range(number_of_tries):
                try:
                    if price is None:
                        price = self.get_price(coin)
                except Exception as e:
                    continue

                body = (f'{{"side":"{side}",'
                        f'"symbol":"{coin}",'
                        f'"orderType":"limit",'
                        f'"marginCoin":"USDT",'
                        f'"price":"{price}",'
                        f'"size":"{quantity}"}}')

                headers = self.create_header(method=method, request_path=request_path, body=body)
                response = requests.post(url="https://api.coincatch.com/api/mix/v1/order/placeOrder",
                                         data=body,
                                         headers=headers)
                remote_id = interpret_response(response.json(), "orderId")

                time.sleep(10)

                state_of_order = self.get_order_information(coin=coin, remote_id=remote_id)
                if state_of_order is None or state_of_order == 'new':
                    canceled_response = self.cancel_order(coin=coin, remote_id=remote_id)
                    if canceled_response == '00000':
                        continue
                    else:
                        raise Exception(f"In canceling limit order got {canceled_response}")
                elif state_of_order == 'filled':
                    return remote_id
                else:
                    raise Exception(f"State of order is {state_of_order}")
        except Exception as e:
            print(e)
        return self.futures_trade(coin, quantity, side)

    def cancel_order(self, coin: Coin.type, remote_id):
        method = "POST"
        request_path = "/api/mix/v1/order/cancel-order"
        body = (f'{{"orderId":"{remote_id}",'
                f'"symbol":"{coin}",'
                f'"marginCoin":"USDT"}}')

        headers = self.create_header(method=method, request_path=request_path, body=body)
        response = requests.post(url="https://api.coincatch.com/api/mix/v1/order/cancel-order",
                                 data=body,
                                 headers=headers)
        return response.json().get('code', None)
    # def change_leverage(self, coin: Coin, leverage: int, direction: PositionDirection):
    #     method = "POST"
    #     request_path = "/api/mix/v1/account/setLeverage"
    #     body = (f'{{"symbol":"{coin.value}",'
    #             f'"marginCoin":"USDT",'
    #             f'"leverage":"{leverage}",'
    #             f'"holdSide":"{direction.value}"}}')
    #     headers = self.create_header(method=method, request_path=request_path, body=body)
    #     response = requests.post(url="https://api.coincatch.com/api/mix/v1/account/setLeverage",
    #                              data=body,
    #                              headers=headers)
    #     print(response.text)
    #     return response

    def place_sltp(self, coin: Coin.type,
                   plan_type: PlanType.type,
                   trigger_price: Decimal,
                   direction: PositionDirection.type,
                   quantity: Decimal):
        method = "POST"
        request_path = "/api/mix/v1/plan/placeTPSL"
        body = (f'{{"symbol":"{coin}",'
                f'"marginCoin":"USDT",'
                f'"size":"{quantity}",'
                f'"planType":"{plan_type}",'
                f'"triggerPrice":"{round(trigger_price, 1)}",'
                f'"holdSide":"{direction}"}}')
        headers = self.create_header(method=method, request_path=request_path, body=body)
        response = requests.post(url="https://api.coincatch.com/api/mix/v1/plan/placeTPSL",
                                 data=body,
                                 headers=headers)
        print(response.text)
        remote_id = interpret_response(response.json(), "orderId")
        return remote_id

    def modify_sltp(self, sltporder, trigger_price: Decimal):
        method = "POST"
        request_path = "/api/mix/v1/plan/modifyTPSLPlan"
        body = (f'{{"symbol":"{sltporder.coin}",'
                f'"marginCoin":"USDT",'
                f'"planType":"{sltporder.plan_type}",'
                f'"triggerPrice":"{round(trigger_price, 1)}",'
                f'"orderId":"{sltporder.remote_id}"}}')
        headers = self.create_header(method=method, request_path=request_path, body=body)
        response = requests.post(url="https://api.coincatch.com/api/mix/v1/plan/modifyTPSLPlan",
                                 data=body,
                                 headers=headers)
        print(response.text)
        response_code = response.json().get('code', None)
        print(f"response_code is {response_code}")
        if response.status_code == 200:
            if response_code == '00000':
                return True
        else:
            if response_code == '43020':
                return "Changed"
            return False

    def cancel_sltp(self, sltporder):
        method = "POST"
        request_path = "/api/mix/v1/plan/cancelPlan"
        body = (f'{{"symbol":"{sltporder.coin}",'
                f'"marginCoin":"USDT",'
                f'"planType":"{sltporder.plan_type}",'
                f'"orderId":"{sltporder.remote_id}"}}')
        headers = self.create_header(method=method, request_path=request_path, body=body)
        response = requests.post(url="https://api.coincatch.com/api/mix/v1/plan/cancelPlan",
                                 data=body,
                                 headers=headers)
        print(response.text)
        if response.status_code == 200:
            return True
        else:
            return False

    def get_price(self, coin: Coin.type):
        method = "GET"
        request_path = "/api/mix/v1/market/mark-price"
        query_string = f'symbol={coin}'
        headers = self.create_header(method=method, request_path=request_path, query_string=query_string)
        response = requests.get(url="https://api.coincatch.com/api/mix/v1/market/mark-price" + "?" + query_string,
                                headers=headers)
        print(response.text)
        if response.status_code != 200:
            raise Exception("Error in get price!")
        return Decimal(response.json().get('data').get('markPrice'))

    def get_position_order_information(self, coin: Coin.type, remote_id: str):
        method = "GET"
        request_path = "/api/mix/v1/order/fills"
        query_string = f'symbol={coin}&orderId={remote_id}'
        headers = self.create_header(method=method, request_path=request_path, query_string=query_string)
        response = requests.get(url="https://api.coincatch.com/api/mix/v1/order/fills" + "?" + query_string,
                                headers=headers)
        print(response.json())
        try:
            data = interpret_response(dictionary=response.json())[0]
        except IndexError:
            raise Exception("No order found")
        output = {
            "price": get_param(data, "price"),
            "quantity": get_param(data, "sizeQty"),
            "fee": get_param(data, "fee"),
            "fill_amount": get_param(data, "fillAmount"),
            "profit": get_param(data, "profit"),
            "side": get_param(data, "side"),
            "created": get_param(data, "cTime"),
        }
        return output

    def get_order_information(self, coin: Coin.type, remote_id: str):
        method = "GET"
        request_path = "/api/mix/v1/order/detail"
        query_string = f'symbol={coin}&orderId={remote_id}'
        headers = self.create_header(method=method, request_path=request_path, query_string=query_string)
        response = requests.get(url="https://api.coincatch.com/api/mix/v1/order/detail" + "?" + query_string,
                                headers=headers)
        response_data = response.json().get('data', None)
        if response_data:
            state = response_data.get('state', None)
            return state
        else:
            return None

    def _create_first_time_go_long(self):
        position = Position.create_new_position(trader=self, coin=Coin.btc_futures.value,
                                                quantity=Decimal("0.003"), side=SideFutures.open_long.value)
        position_action = position.positionaction_set.last()
        sl_price = position_action.price * Decimal("0.99")
        tp_price_1 = position_action.price * Decimal("1.005")
        tp_price_2 = position_action.price * Decimal("1.01")
        tp_price_3 = position_action.price * Decimal("1.02")

        sl_order = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                   trigger_price=sl_price, quantity=position.quantity,
                                                   plan_type=PlanType.sl.value)
        tp_order_1 = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                     trigger_price=tp_price_1,
                                                     quantity=position.quantity / Decimal("3"),
                                                     plan_type=PlanType.tp.value)
        tp_order_2 = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                     trigger_price=tp_price_2,
                                                     quantity=position.quantity / Decimal("3"),
                                                     plan_type=PlanType.tp.value)
        tp_order_3 = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                     trigger_price=tp_price_3,
                                                     quantity=position.quantity / Decimal("3"),
                                                     plan_type=PlanType.tp.value)
        monitoring_sltp_orders.apply_async(args=[position.id])

    def _create_first_time_go_long_v2(self):
        position = Position.create_new_position(trader=self, coin=Coin.btc_futures.value,
                                                quantity=Decimal("0.003"), side=SideFutures.open_long.value)
        position_action = position.positionaction_set.last()
        sl_price = position_action.price * Decimal("0.995")
        tp_price = position_action.price * Decimal("1.005")

        sl_order = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                   trigger_price=sl_price, quantity=position.quantity,
                                                   plan_type=PlanType.sl.value)
        tp_order = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                   trigger_price=tp_price,
                                                   quantity=position.quantity,
                                                   plan_type=PlanType.tp.value)

        monitoring_sltp_orders.apply_async(args=[position.id])

    def _calculate_second_time_price(self, position, position_previous_quantity):
        position_actions = position.positionaction_set
        return (position_previous_quantity * position_actions.first().price +
                Decimal("0.003") * position_actions.last().price) / (position_previous_quantity + Decimal("0.003"))

    def _create_second_time_go_long(self, position):
        write_at_cache(position.id, "changing", f"second_time_go_long for {self.name}")
        position_previous_quantity = position.quantity
        position.expand_position(quantity=Decimal("0.003"))
        position.cancel_all_sltp_orders()
        price = self._calculate_second_time_price(position=position,
                                                  position_previous_quantity=position_previous_quantity)
        sl_price = price * Decimal("0.99")
        tp_price_1 = price * Decimal("1.005")
        tp_price_2 = price * Decimal("1.01")
        tp_price_3 = price * Decimal("1.02")
        sl_order = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                   trigger_price=sl_price, quantity=position.quantity,
                                                   plan_type=PlanType.sl.value)
        tp_order_1 = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                     trigger_price=tp_price_1,
                                                     quantity=Decimal("0.002"),
                                                     plan_type=PlanType.tp.value)
        tp_order_2 = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                     trigger_price=tp_price_2,
                                                     quantity=Decimal("0.002"),
                                                     plan_type=PlanType.tp.value)
        if position.quantity > Decimal("0.0041"):
            tp_order_3 = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                         trigger_price=tp_price_3,
                                                         quantity=position.quantity - Decimal("0.004"),
                                                         plan_type=PlanType.tp.value)
        write_at_cache(position.id, "finished", f"second_time_go_long finished for {self.name}")

    def _create_first_time_go_short(self):
        position = Position.create_new_position(trader=self, coin=Coin.btc_futures.value,
                                                quantity=Decimal("0.003"), side=SideFutures.open_short.value)
        position_action = position.positionaction_set.last()
        sl_price = position_action.price * Decimal("1.01")
        tp_price_1 = position_action.price * Decimal("0.995")
        tp_price_2 = position_action.price * Decimal("0.99")
        tp_price_3 = position_action.price * Decimal("0.98")

        sl_order = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                   trigger_price=sl_price, quantity=position.quantity,
                                                   plan_type=PlanType.sl.value)
        tp_order_1 = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                     trigger_price=tp_price_1,
                                                     quantity=position.quantity / Decimal("3"),
                                                     plan_type=PlanType.tp.value)
        tp_order_2 = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                     trigger_price=tp_price_2,
                                                     quantity=position.quantity / Decimal("3"),
                                                     plan_type=PlanType.tp.value)
        tp_order_3 = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                     trigger_price=tp_price_3,
                                                     quantity=position.quantity / Decimal("3"),
                                                     plan_type=PlanType.tp.value)

        monitoring_sltp_orders.apply_async(args=[position.id])
        # check_position_one_hour_later.apply_async(args=[position.id])

    def _create_first_time_go_short_v2(self):
        position = Position.create_new_position(trader=self, coin=Coin.btc_futures.value,
                                                quantity=Decimal("0.003"), side=SideFutures.open_short.value)
        position_action = position.positionaction_set.last()
        sl_price = position_action.price * Decimal("1.005")
        tp_price = position_action.price * Decimal("0.995")

        sl_order = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                   trigger_price=sl_price, quantity=position.quantity,
                                                   plan_type=PlanType.sl.value)
        tp_order = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                   trigger_price=tp_price,
                                                   quantity=position.quantity,
                                                   plan_type=PlanType.tp.value)

        monitoring_sltp_orders.apply_async(args=[position.id])

    def _create_second_time_go_short(self, position):
        write_at_cache(position.id, "changing", f"second_time_go_long for {self.name}")
        position_previous_quantity = position.quantity
        position.expand_position(quantity=Decimal("0.003"))
        position.cancel_all_sltp_orders()
        position_action = position.positionaction_set.last()
        price = self._calculate_second_time_price(position=position, position_previous_quantity=position_previous_quantity)
        sl_price = price * Decimal("1.01")
        tp_price_1 = price * Decimal("0.995")
        tp_price_2 = price * Decimal("0.99")
        tp_price_3 = price * Decimal("0.98")
        sl_order = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                   trigger_price=sl_price, quantity=position.quantity,
                                                   plan_type=PlanType.sl.value)
        tp_order_1 = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                     trigger_price=tp_price_1,
                                                     quantity=Decimal("0.002"),
                                                     plan_type=PlanType.tp.value)
        tp_order_2 = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                     trigger_price=tp_price_2,
                                                     quantity=Decimal("0.002"),
                                                     plan_type=PlanType.tp.value)
        if position.quantity > Decimal("0.0041"):
            tp_order_3 = SLTPOrder.create_new_sltp_order(trader=self, position=position, coin=Coin.btc_futures.value,
                                                         trigger_price=tp_price_3,
                                                         quantity=position.quantity - Decimal("0.004"),
                                                         plan_type=PlanType.tp.value)
        write_at_cache(position.id, "finished", f"second_time_go_long finished for {self.name}")

    def get_long_sign(self, just_close: bool):
        active_positions = self.position_set.filter(state=State.Active.value)
        number = active_positions.count()
        print(f"number of active_positions: {number}")
        if number > 1:
            raise Exception(f"Not suitable number of active positions: {number}!")
        # elif number == 1:
        #     position = active_positions.last()
        #     if position.direction == PositionDirection.short.value:
        #         position.close_position()
        #         self._create_first_time_go_long()
        #     elif position.direction == PositionDirection.long.value:
        #         with transaction.atomic():
        #             position = Position.objects.filter(id=position.id).select_for_update().get()
        #             if position.number_of_openings >= 2:
        #                 return
        #             else:
        #                 self._create_second_time_go_long(position=position)
        elif number == 1:
            position = active_positions.last()
            if position.direction == PositionDirection.short.value:
                position.close_position()
                if just_close is False:
                    self._create_first_time_go_long_v2()
        elif number == 0:
            self._create_first_time_go_long_v2()

    def get_short_sign(self, just_close: bool):
        active_positions = self.position_set.filter(state=State.Active.value)
        number = active_positions.count()
        print(f"number of active_positions: {number}")
        if number > 1:
            raise Exception(f"Not suitable number of active positions: {number}!")
        # elif number == 1:
        #     position = active_positions.last()
        #     if position.direction == PositionDirection.long.value:
        #         position.close_position()
        #         self._create_first_time_go_short()
        #     elif position.direction == PositionDirection.short.value:
        #         with transaction.atomic():
        #             position = Position.objects.filter(id=position.id).select_for_update().get()
        #             if position.number_of_openings >= 2:
        #                 return
        #             else:
        #                 self._create_second_time_go_short(position=position)
        elif number == 1:
            position = active_positions.last()
            if position.direction == PositionDirection.long.value:
                position.close_position()
                if just_close is False:
                    self._create_first_time_go_short_v2()
        elif number == 0:
            self._create_first_time_go_short_v2()


class Position(BaseModel):
    trader = models.ForeignKey(Trader, on_delete=models.DO_NOTHING)
    pnl = models.DecimalField(max_digits=10, decimal_places=5, default=0, null=True, blank=True)
    coin = models.CharField(
        max_length=50,
        choices=Coin.choices()
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    state = models.IntegerField(choices=State.choices(), null=True, blank=True)
    direction = models.CharField(
        max_length=50,
        choices=PositionDirection.choices()
    )
    is_ever_updated = models.BooleanField(default=False)
    number_of_openings = models.IntegerField(default=0)

    def __str__(self):
        return f'{self.trader.name} {self.direction}'

    def update_position_and_create_position_action(self, remote_id: str):
        print(f"remote_id for trader {self.trader.name} is {remote_id}")
        time.sleep(2)
        order_detail = self.trader.get_position_order_information(coin=self.coin, remote_id=remote_id)
        price = Decimal(order_detail.get('price'))
        fee = Decimal(order_detail.get('fee'))
        quantity = Decimal(order_detail.get('quantity'))
        side = order_detail.get('side')
        profit = Decimal(order_detail.get('profit'))

        if side != SideFutures.open_long.value and side != SideFutures.open_short.value\
                and side != SideFutures.close_long.value and side != SideFutures.close_short.value:
            side = SideFutures.unknown.value

        with transaction.atomic():
            position_action = PositionAction.objects.create(position=self, trader=self.trader, price=price,
                                                            fee=fee, quantity=quantity, remote_id=remote_id,
                                                            profit=profit, coin=self.coin, action_side=side
                                                            )
            pos_quantity = self.quantity
            if self.is_ever_updated is False:
                self.add_comment(f"Created position quantity: {quantity}, side: {side}")
                self.is_ever_updated = True
            else:
                if side == SideFutures.open_long.value or side == SideFutures.open_short.value:
                    pos_quantity += quantity
                    self.add_comment(f"Add quantity: {quantity} in update position.")
                elif side == SideFutures.close_long.value or side == SideFutures.close_short.value:
                    pos_quantity -= quantity
                    self.add_comment(f"Decrease quantity: {quantity} in update position.")
                else:
                    pass

            if pos_quantity <= 0:
                self.state = State.Inactive.value
            self.quantity = pos_quantity
            self.pnl += profit + fee
            self.save(update_fields=["quantity", "pnl", "is_ever_updated", "state", "updated"])
            return position_action

    @staticmethod
    def create_new_position(trader: Trader, coin: Coin.type, quantity: Decimal, side: SideFutures.type):
        remote_id = trader.futures_trade(coin=coin, quantity=quantity, side=side)
        print(f"remote_id is {remote_id} for {trader.name} in creating new_position")
        position = Position.objects.create(trader=trader, coin=coin, quantity=quantity, state=State.Active.value,
                                           direction=SideFutures.get_position_direction(side))
        position.update_position_and_create_position_action(remote_id=remote_id)
        position.state = State.Active.value
        position.number_of_openings += 1
        position.save(update_fields=["state", "number_of_openings", "updated"])
        return position

    def inactivate_all_sltp_orders(self):
        all_sltp_orders = self.sltporder_set.filter(state=State.Active.value)
        for order in all_sltp_orders:
            order.inactivate()

    def close_position(self):
        write_at_cache(self.id, "changing", f"close position started for {self.trader.name}")
        self.add_comment("Close position started")
        side = SideFutures.close_long.value if self.direction == PositionDirection.long.value else\
            SideFutures.close_short.value
        remote_id = self.trader.futures_trade(coin=self.coin, quantity=self.quantity, side=side)
        self.update_position_and_create_position_action(remote_id=remote_id)
        self.inactivate_all_sltp_orders()
        self.state = State.Inactive.value
        self.save(update_fields=['state', 'updated'])
        write_at_cache(self.id, "finished", f"closed position finished for {self.trader.name}")
        self.add_comment("Position closed")

    def expand_position(self, quantity: Decimal):
        side = SideFutures.open_long.value if self.direction == PositionDirection.long.value else \
            SideFutures.open_short.value
        remote_id = self.trader.futures_trade(coin=self.coin, quantity=quantity, side=side)
        print(f"remote_id is {remote_id} for {self.trader.name} in expanding position.")
        self.number_of_openings += 1
        self.save(update_fields=["number_of_openings", "updated"])
        self.add_comment(f"Expanding position with quantity: {quantity}")
        position_action = self.update_position_and_create_position_action(remote_id=remote_id)
        return position_action

    def cancel_all_sltp_orders(self):
        self.add_comment("Start cancelling all sltp orders.")
        sltp_orders = self.sltporder_set.filter(state=State.Active.value)
        for sltp_order in sltp_orders:
            sltp_order.cancel_sltp_order()

        self.add_comment("All sltp orders canceled")


class PositionAction(BaseModel):
    position = models.ForeignKey(Position, on_delete=models.DO_NOTHING)
    trader = models.ForeignKey(Trader, on_delete=models.DO_NOTHING)
    action_side = models.CharField(
        max_length=50,
        choices=SideFutures.choices()
    )
    price = models.DecimalField(max_digits=10, decimal_places=1)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    coin = models.CharField(
        max_length=50,
        choices=Coin.choices()
    )
    remote_id = models.CharField(max_length=200)
    profit = models.DecimalField(max_digits=10, decimal_places=5)
    fee = models.DecimalField(max_digits=10, decimal_places=5, default=0)

    def __str__(self):
        return f'{self.trader.name} {self.action_side} {self.quantity}'


class SLTPOrder(BaseModel):
    trader = models.ForeignKey(Trader, on_delete=models.DO_NOTHING)
    position = models.ForeignKey(Position, on_delete=models.DO_NOTHING, db_constraint=False)
    coin = models.CharField(
        max_length=50,
        choices=Coin.choices()
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    plan_type = models.CharField(
        max_length=50,
        choices=PlanType.choices()
    )
    trigger_price = models.DecimalField(max_digits=10, decimal_places=1, null=True, blank=True)
    state = models.IntegerField(choices=State.choices())
    remote_id = models.CharField(max_length=200)

    def __str__(self):
        return f'{self.coin} {self.plan_type} {self.trader.name}'

    @staticmethod
    def create_new_sltp_order(trader: Trader, position: Position, coin: Coin.type,
                              trigger_price: Decimal, quantity: Decimal, plan_type: PlanType.type):

        remote_id = trader.place_sltp(coin=coin, trigger_price=trigger_price, direction=position.direction,
                                      quantity=quantity, plan_type=plan_type)
        sltp_order = SLTPOrder.objects.create(trader=trader, position=position, coin=coin,
                                              remote_id=remote_id, quantity=quantity, plan_type=plan_type,
                                              trigger_price=trigger_price, state=State.Active.value)
        sltp_order.position.add_comment(f"Created with quantity: {sltp_order.quantity} at trigger price: "
                                        f"{sltp_order.trigger_price}")
        return sltp_order

    def change_trigger_price(self, new_trigger_price: Decimal):
        changed = self.trader.modify_sltp(sltporder=self, trigger_price=new_trigger_price)
        if changed:
            self.trigger_price = new_trigger_price
            self.save(update_fields=["trigger_price", "updated"])

    def cancel_sltp_order(self):
        canceled = self.trader.cancel_sltp(sltporder=self)
        if canceled:
            self.inactivate()

    def get_information(self):
        state = read_from_cache(self.position.id, f"{self.trader.name} {self.plan_type}")
        if state == "changing":
            return False
        self.refresh_from_db()
        print(f"Getting information for {self.trader.name} {self.plan_type} with state {self.state} -> {datetime.now()}")
        if self.state != State.Active.value:
            return False
        try:
            modified = self.trader.modify_sltp(sltporder=self, trigger_price=self.trigger_price)
            print(modified)
            if modified == "Changed":
                self.inactivate()
                return True
            return False
        except Exception as e:
            print(e)
            return False

    def inactivate(self):
        self.state = State.Inactive.value
        self.save(update_fields=["state", "updated"])
        self.position.add_comment(f"{self.plan_type} order inactivated.")
