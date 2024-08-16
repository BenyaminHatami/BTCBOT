from datetime import datetime
from decimal import Decimal

import traceback

from celery import shared_task
from django.core.cache import cache
import time


# @shared_task
# def inquiry_task():
#     from Logic.models import Trader, Coin
#     trader = Trader.objects.get(id=1)
#     price = trader.get_price(coin=Coin.btc_futures.value)
#     cache.set("price", price)


@shared_task
def change_sl_with_price(position_id: int):
    from Logic.models import Position, PlanType, State
    print("STARTED TASK")
    position = Position.objects.get(id=position_id)
    entry_price = position.positionaction_set.last().price
    while True:
        print("OKAY")
        if position.state == State.Inactive.value:
            break
        time.sleep(1)
        price = cache.get("price")
        if price is not None:
            if abs(entry_price - price) >= 50:
                sl_order = position.sltporder_set.filter(plan_type=PlanType.sl.value).get()
                new_price = entry_price * Decimal("0.995")
                sl_order.change_trigger_price(new_trigger_price=new_price)
                break


@shared_task
def get_long_sign_task(trader_id: int):
    from Logic.models import Trader
    trader = Trader.objects.get(id=trader_id)
    try:
        trader.get_long_sign()
    except Exception as ve:
        print(ve.__str__() + "\n" + str(traceback.format_exc()))


@shared_task
def get_short_sign_task(trader_id: int):
    from Logic.models import Trader
    trader = Trader.objects.get(id=trader_id)
    try:
        trader.get_short_sign()
    except Exception as ve:
        print(ve.__str__() + "\n" + str(traceback.format_exc()))


@shared_task
def monitoring_sltp_orders(position_id: int):
    from Logic.models import Position, State, PlanType, PositionDirection
    while True:
        print("STARTED TASK")
        position = Position.objects.get(id=position_id)
        price = position.positionaction_set.last().price
        active_sltp_orders = position.sltporder_set.filter(state=State.Active.value)
        if len(active_sltp_orders) == 0:
            break
        sls = active_sltp_orders.filter(plan_type=PlanType.sl.value)
        assert len(sls) == 1
        sl = sls.last()
        inactivated = sl.get_information()
        if inactivated:
            position.inactivate_all_sltp_orders()
            position.state = State.Inactive.value
            position.quantity -= sl.quantity
            position.add_comment(f"Quantity decreased duo to stop loss with quantity: {sl.quantity}")
            position.save(update_fields=["state", "quantity", "updated"])
            return

        if position.direction == PositionDirection.long.value:
            sorted_tps = active_sltp_orders.filter(plan_type=PlanType.tp.value).order_by('trigger_price')
            number_of_tps = len(sorted_tps)
            assert number_of_tps <= 2
            if number_of_tps == 2:
                for i in range(2):
                    tp = sorted_tps[i]
                    inactivated = tp.get_information()
                    if inactivated and i == 0:
                        sl.change_trigger_price(new_trigger_price=price)
                        tp.inactivate()
                        position.quantity -= tp.quantity
                        position.add_comment(f"Quantity decreased duo to first tp with quantity: {tp.quantity}")
                        position.save(update_fields=["quantity", "updated"])
                    elif inactivated and i == 1:
                        position.inactivate_all_sltp_orders()
                        position.state = State.Inactive.value
                        position.quantity -= tp.quantity
                        position.add_comment(f"Quantity decreased duo to second tp with quantity: {tp.quantity}")
                        position.save(update_fields=["state", "quantity", "updated"])
                        return
            elif number_of_tps == 1:
                tp = sorted_tps[0]
                inactivated = tp.get_information()
                if inactivated:
                    position.inactivate_all_sltp_orders()
                    position.state = State.Inactive.value
                    position.quantity -= tp.quantity
                    position.add_comment(f"Quantity decreased duo to the only tp with quantity: {tp.quantity}")
                    position.save(update_fields=["state", "quantity", "updated"])
                    return
            else:
                raise Exception(f"No tps!? {position_id}")

        elif position.direction == PositionDirection.short.value:
            sorted_tps = active_sltp_orders.filter(plan_type=PlanType.tp.value).order_by('-trigger_price')
            number_of_tps = len(sorted_tps)
            assert number_of_tps <= 2
            if number_of_tps == 2:
                for i in range(2):
                    tp = sorted_tps[i]
                    inactivated = tp.get_information()
                    if inactivated and i == 0:
                        sl.change_trigger_price(new_trigger_price=price)
                        tp.inactivate()
                        position.quantity -= tp.quantity
                        position.add_comment(f"Quantity decreased duo to first tp with quantity: {tp.quantity}")
                        position.save(update_fields=["quantity", "updated"])
                    elif inactivated and i == 1:
                        position.inactivate_all_sltp_orders()
                        position.state = State.Inactive.value
                        position.quantity -= tp.quantity
                        position.add_comment(f"Quantity decreased duo to second tp with quantity: {tp.quantity}")
                        position.save(update_fields=["state", "quantity", "updated"])
                        return
            elif number_of_tps == 1:
                tp = sorted_tps[0]
                inactivated = tp.get_information()
                if inactivated:
                    position.inactivate_all_sltp_orders()
                    position.state = State.Inactive.value
                    position.quantity -= tp.quantity
                    position.add_comment(f"Quantity decreased duo to the only tp with quantity: {tp.quantity}")
                    position.save(update_fields=["state", "quantity", "updated"])
                    return
            else:
                raise Exception(f"No tps!? {position_id}")

        time.sleep(5)
