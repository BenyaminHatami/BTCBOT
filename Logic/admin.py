from django.contrib import admin
from Logic.models import Trader, Position, SLTPOrder, PositionAction


@admin.register(Trader)
class TraderAdmin(admin.ModelAdmin):
    list_display = ("name", "pnl")


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("created", "updated", "trader", "direction", "pnl", "coin", "quantity", "state", "is_ever_updated")


@admin.register(SLTPOrder)
class SLTPOrderAdmin(admin.ModelAdmin):
    list_display = ("created", "updated", "position", "coin", "quantity", "plan_type", "trigger_price", "state")


@admin.register(PositionAction)
class PositionActionAdmin(admin.ModelAdmin):
    list_display = ("created", "updated", "trader", "position", "action_side", "price", "quantity", "coin", "remote_id",
                    "profit", "fee")

