from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import *
from .tasks import get_long_sign_task, get_short_sign_task
import traceback


class LongView(APIView):

    def post(self, request):
        traders = Trader.objects.all()
        for trader in traders:
            try:
                get_long_sign_task.apply_async(kwargs={"trader_id": trader.id}, soft_time_limit=30, time_limit=34)
            except Exception as e:
                print(e.__str__() + "\n" + str(traceback.format_exc()))
                print(f'trader.name: {trader.name}')

        return Response(data={"msg": "Okay"}, status=status.HTTP_200_OK)


class ShortView(APIView):

    def post(self, request):
        traders = Trader.objects.all()
        for trader in traders:
            try:
                get_short_sign_task.apply_async(kwargs={"trader_id": trader.id}, soft_time_limit=20, time_limit=22)
            except Exception as e:
                print(e.__str__() + "\n" + str(traceback.format_exc()))

        return Response(data={"msg": "Okay"}, status=status.HTTP_200_OK)


class GetPositionState(APIView):

    def get(self, request):
        have_any_active_positions = False
        position_type = None
        for trader in Trader.objects.all():
            position: Position = trader.position_set.filter(state=State.Active.value).last()
            if position:
                have_any_active_positions = True
                position_type = position.direction
                break

        return Response(data={"active_position": have_any_active_positions, "position_type": position_type},
                        status=status.HTTP_200_OK)
