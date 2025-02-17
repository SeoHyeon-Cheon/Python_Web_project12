import json
import re
import random
import string
import requests  # 실제 API 호출 시 사용
from datetime import datetime, timedelta  # 추가: 날짜 계산을 위해
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.core.paginator import Paginator
from .models import Signup, Planner, Tourlist, PlannerDetail, Board, Comment
from django.core.mail import send_mail  # 실제 메일 전송 시 사용 (설정 필요)
from django.contrib.auth.hashers import make_password, check_password  # 해시 처리를 위한 함수
from django.contrib import messages


def main_page(request):
    regions = [
        {"name": "서울", "img": "seoul.jpg"},
        {"name": "부산", "img": "busan.jpg"},
        {"name": "제주도", "img": "jeju.jpg"},
        {"name": "강릉", "img": "gangneung.jpg"},
        {"name": "경주", "img": "gyeongju.jpg"},
        {"name": "영월", "img": "yeongwol.jpg"},
        {"name": "전주", "img": "jeonju.jpg"},
        {"name": "여수", "img": "yeosu.jpg"},
        {"name": "인천", "img": "incheon.jpg"},
        {"name": "속초", "img": "sokcho.jpg"},
        {"name": "대구", "img": "daegu.jpg"},
        {"name": "춘천", "img": "chuncheon.jpg"}
    ]
    context = {
        "regions": regions,
    }
    return render(request, "planner/main_page.html", context)


@csrf_exempt
def signup_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')
        name = request.POST.get('name')
        birth = request.POST.get('birth')
        addr = request.POST.get('addr')
        phone_num = request.POST.get('phone_num')

        # 서버 측 검증

        # 이메일 검증
        var_email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not re.match(var_email_pattern, email):
            return JsonResponse({'status': 'error', 'message': '유효하지 않은 이메일 형식입니다.'}, status=400)

        # 비밀번호 검증: 8~16자, 영문 대소문자, 숫자, 특수문자 포함
        var_password_pattern = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};\'":\\|,.<>\/?]).{8,16}$'
        if not re.match(var_password_pattern, password):
            return JsonResponse({'status': 'error', 'message': '비밀번호는 8~16자 영문 대소문자, 숫자, 특수문자를 포함해야 합니다.'}, status=400)

        if password != password_confirm:
            return JsonResponse({'status': 'error', 'message': '비밀번호와 비밀번호 재확인이 일치하지 않습니다.'}, status=400)

        # 중복 가입 검사:
        # 만약 해당 이메일로 가입한 사용자가 있다면,
        # - is_active가 True이면 이미 가입된 계정이므로 에러를 반환하고,
        # - is_active가 False이면 해당 레코드를 업데이트하여 재가입(재활성화) 처리
        try:
            existing_user = Signup.objects.get(email=email)
            if existing_user.is_active:
                return JsonResponse({'status': 'error', 'message': '이미 가입된 이메일입니다.'}, status=400)
            else:
                # 탈퇴된 계정이면 업데이트하여 재가입 처리
                existing_user.password = make_password(password)
                existing_user.name = name
                existing_user.birth = birth if birth else None
                existing_user.addr = addr
                existing_user.phone_num = phone_num
                existing_user.is_active = True
                existing_user.save()
                return JsonResponse({'status': 'success', 'message': '회원가입 성공'})
        except Signup.DoesNotExist:
            # 존재하지 않는 경우에는 새로 생성
            Signup.objects.create(
                email=email,
                password=make_password(password),
                name=name,
                birth=birth if birth else None,
                addr=addr,
                phone_num=phone_num,
                is_active=True
            )
            return JsonResponse({'status': 'success', 'message': '회원가입 성공'})
    else:
        return render(request, 'planner/signup.html')


@csrf_exempt
def login_view(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        try:
            user = Signup.objects.get(email=email)
            # 활성화 상태가 아니면 로그인 실패 처리
            if not user.is_active:
                return JsonResponse({"status": "error", "message": "아이디 또는 비밀번호가 올바르지 않습니다."}, status=403)
            if check_password(password, user.password):
                request.session["user_email"] = user.email
                request.session["user_name"] = user.name
                return JsonResponse({"status": "success", "user_name": user.name})
            else:
                raise Signup.DoesNotExist
        except Signup.DoesNotExist:
            return JsonResponse({"status": "error", "message": "아이디 또는 비밀번호가 올바르지 않습니다."}, status=400)
    else:
        return JsonResponse({"status": "error", "message": "POST 요청만 허용됩니다."}, status=405)


def logout_view(request):
    request.session.flush()  # 세션 데이터 초기화
    return redirect('main_page')


@csrf_exempt
def password_reset_view(request):
    """
    비밀번호 찾기:
    사용자가 본인의 이메일과 이름을 입력하면, 해당 회원 정보를 확인하고,
    임시 비밀번호(8자리)를 생성하여 회원의 비밀번호를 해시 처리한 후 업데이트하고,
    전용 발신자 계정을 사용하여 임시 비밀번호를 이메일로 전송합니다.
    """
    if request.method == "POST":
        email = request.POST.get("email")
        name = request.POST.get("name")
        try:
            user = Signup.objects.get(email=email, name=name)
        except Signup.DoesNotExist:
            return JsonResponse({"status": "error", "message": "해당 회원 정보를 찾을 수 없습니다."}, status=400)

        # 임시 비밀번호 생성 (8자리)
        temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))

        # 비밀번호 해시 처리 후 업데이트
        user.password = make_password(temp_password)
        user.save()

        # 이메일 전송 (전용 발신자 계정을 사용하여 settings.py의 EMAIL 설정에 따라 처리됨)
        subject = "여행 플래너 임시 비밀번호 안내"
        message = (
            f"안녕하세요, {user.name}님.\n\n"
            f"요청하신 임시 비밀번호는 {temp_password} 입니다.\n"
            "로그인 후 반드시 비밀번호를 변경해 주세요.\n\n"
            "감사합니다."
        )
        recipient_list = [user.email]

        try:
            send_mail(subject, message, None, recipient_list, fail_silently=False)
            # 발신자 정보를 생략하면 settings.py의 DEFAULT_FROM_EMAIL이 사용됩니다.
        except Exception as e:
            return JsonResponse({"status": "error", "message": f"이메일 전송에 실패했습니다: {e}"}, status=500)

        return JsonResponse({"status": "success", "message": "임시 비밀번호가 이메일로 전송되었습니다. 이메일을 확인해 주세요."})
    else:
        return render(request, 'planner/password_reset.html')


def search_view(request):
    """
    검색 페이지:
    사용자가 여행지명을 입력하여 검색할 수 있도록 하는 페이지입니다.
    폼 제출 시 GET 방식으로 plan_schedule 뷰에 destination 파라미터를 전달합니다.
    """
    return render(request, 'planner/search.html')


def my_page_view(request):
    """
    마이페이지: 로그인한 사용자의 회원정보와 '나의 일정'을 함께 표시합니다.
    """
    user_email = request.session.get('user_email')
    if not user_email:
        return redirect('login')
    try:
        user = Signup.objects.get(email=user_email)
    except Signup.DoesNotExist:
        return redirect('login')

    # Planner 테이블에는 직접 user 정보가 없으므로, PlannerDetail을 통해 연결된 Planner들을 가져옵니다.
    planners = Planner.objects.filter(plannerdetail__signup=user).distinct()
    current_date = timezone.now().date()

    # Planner.edate를 기준으로 다가올 여행 일정과 지난 여행 일정을 구분합니다.
    upcoming_plans = planners.filter(edate__gte=current_date).order_by("sdate")
    past_plans = planners.filter(edate__lt=current_date).order_by("-sdate")

    # 각 Planner에 대해 여행 제목은 PlannerDetail의 plan_name (예: "서울여행 - ...")에서 추출합니다.
    def get_travel_title(plan):
        detail = plan.plannerdetail_set.order_by("wdate").first()
        if detail:
            return detail.plan_name
        return plan.region  # 없으면 지역명을 대체값으로 사용

    upcoming_list = []
    for plan in upcoming_plans:
        upcoming_list.append({
            "plan_no": plan.plan_no,
            "travel_title": get_travel_title(plan),
            "plan_img": plan.plan_img,
            "sdate": plan.sdate,
            "edate": plan.edate,
            "region": plan.region,
        })

    past_list = []
    for plan in past_plans:
        past_list.append({
            "plan_no": plan.plan_no,
            "travel_title": get_travel_title(plan),
            "plan_img": plan.plan_img,
            "sdate": plan.sdate,
            "edate": plan.edate,
            "region": plan.region,
        })

    context = {
        "user": user,
        "upcoming_plans": upcoming_list,
        "past_plans": past_list,
    }
    return render(request, "planner/my_page.html", context)


def my_schedule_view(request):
    # 로그인 체크: 로그인하지 않은 경우 로그인 페이지로 리다이렉트
    user_email = request.session.get("user_email")
    if not user_email:
        return redirect("login")
    try:
        user = Signup.objects.get(email=user_email)
    except Signup.DoesNotExist:
        return redirect("login")

    # Planner 테이블에는 직접 user 정보가 없으므로, PlannerDetail에서 연결된 Planner들을 가져옵니다.
    # 각 PlannerDetail은 signup 필드를 가지고 있으므로, 사용자가 작성한 PlannerDetail을 통해 Planner를 추출합니다.
    planners = Planner.objects.filter(plannerdetail__signup=user).distinct()

    # 현재 날짜 (timezone.now()를 date()로 변환)
    current_date = timezone.now().date()

    # Planner.edate(여행 종료일)을 기준으로 다가올 여행과 과거 여행을 구분합니다.
    upcoming_plans = planners.filter(edate__gte=current_date).order_by("sdate")
    past_plans = planners.filter(edate__lt=current_date).order_by("-sdate")

    # 각 Planner에 대해 여행 제목을 추출합니다.
    # PlannerDetail의 plan_name은 "여행제목 - ..." 형태로 생성되었다고 가정합니다.
    def get_travel_title(plan):
        detail = plan.plannerdetail_set.order_by("wdate").first()
        if detail:
            return detail.plan_name
        return plan.region  # 없으면 지역명을 대체값으로 사용

    # 여행 목록을 리스트 형태로 준비합니다.
    upcoming_list = []
    for plan in upcoming_plans:
        upcoming_list.append({
            "plan_no": plan.plan_no,
            "travel_title": get_travel_title(plan),
            "plan_img": plan.plan_img,  # 이미지 경로; 없으면 템플릿에서 기본 이미지를 처리
            "sdate": plan.sdate,
            "edate": plan.edate,
            "region": plan.region,
        })

    past_list = []
    for plan in past_plans:
        past_list.append({
            "plan_no": plan.plan_no,
            "travel_title": get_travel_title(plan),
            "plan_img": plan.plan_img,
            "sdate": plan.sdate,
            "edate": plan.edate,
            "region": plan.region,
        })

    context = {
        "upcoming_plans": upcoming_list,
        "past_plans": past_list,
    }
    return render(request, "planner/my_schedule.html", context)


@csrf_protect
def schedule_detail_view(request, plan_no):
    """
    특정 일정(Planner)의 상세 내용을 보여주는 페이지입니다.

    PlannerDetail 테이블의 모든 항목을 해당 Planner에 대해 조회하고,
    wdate(일정 날짜)를 기준으로 그룹화하여 각 날짜별 일정 목록을 템플릿에 전달합니다.

    템플릿에서는 Planner(여행 일정) 정보와 함께, 각 날짜별(예: DAY 1, DAY 2, …) 일정 항목(관광지명, 메모 등)을 리스트 형태로 표시합니다.
    """
    # plan_no로 Planner 객체를 가져옵니다. (없으면 404)
    planner = get_object_or_404(Planner, plan_no=plan_no)

    # 해당 Planner에 연결된 PlannerDetail 항목들을 wdate 기준 오름차순으로 조회합니다.
    details = PlannerDetail.objects.filter(planner=planner).order_by('wdate')

    # wdate(일정 날짜)를 기준으로 PlannerDetail 항목들을 그룹화합니다.
    itinerary_by_day = {}
    for detail in details:
        day = detail.wdate  # detail.wdate는 date 타입입니다.
        itinerary_by_day.setdefault(day, []).append(detail)

    # 그룹화된 날짜들을 정렬합니다.
    sorted_days = sorted(itinerary_by_day.keys())

    context = {
        "planner": planner,
        "itinerary_by_day": itinerary_by_day,
        "sorted_days": sorted_days,
    }
    return render(request, "planner/schedule_detail.html", context)

@csrf_exempt
def update_profile_view(request):
    """
    회원정보 수정: 로그인한 사용자의 정보를 업데이트합니다.
    선택적으로 새 비밀번호와 새 비밀번호 재확인을 입력하여 비밀번호를 변경할 수 있습니다.
    """
    user_email = request.session.get('user_email')
    if not user_email:
        return JsonResponse({"status": "error", "message": "로그인이 필요합니다."}, status=401)
    try:
        user = Signup.objects.get(email=user_email)
    except Signup.DoesNotExist:
        return JsonResponse({"status": "error", "message": "회원 정보를 찾을 수 없습니다."}, status=400)

    if request.method == 'POST':
        user.name = request.POST.get('name', user.name)
        user.addr = request.POST.get('addr', user.addr)
        user.phone_num = request.POST.get('phone_num', user.phone_num)
        birth = request.POST.get('birth')
        if birth:
            user.birth = birth

        # 새 비밀번호 업데이트 (선택적)
        new_password = request.POST.get('new_password')
        new_password_confirm = request.POST.get('new_password_confirm')
        if new_password or new_password_confirm:
            if new_password != new_password_confirm:
                return JsonResponse({"status": "error", "message": "새 비밀번호와 재확인이 일치하지 않습니다."}, status=400)
            # 비밀번호 형식 검증: 8~16자, 영문 대소문자, 숫자, 특수문자 포함
            var_password_pattern = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};\'":\\|,.<>\/?]).{8,16}$'
            if not re.match(var_password_pattern, new_password):
                return JsonResponse({"status": "error", "message": "새 비밀번호는 8~16자 영문 대소문자, 숫자, 특수문자를 포함해야 합니다."},
                                    status=400)
            user.password = make_password(new_password)

        user.save()
        return JsonResponse({"status": "success", "message": "회원정보가 업데이트 되었습니다."})
    else:
        return render(request, 'planner/update_profile.html', {'user': user})


@csrf_exempt
def delete_profile_view(request):
    """
    회원탈퇴: 로그인한 사용자가 자신의 회원정보를 탈퇴 처리합니다.
    실제로 데이터를 삭제하는 대신, is_active 값을 False로 설정합니다.
    """
    user_email = request.session.get('user_email')
    if not user_email:
        return JsonResponse({"status": "error", "message": "로그인이 필요합니다."}, status=401)
    try:
        user = Signup.objects.get(email=user_email)
    except Signup.DoesNotExist:
        return JsonResponse({"status": "error", "message": "회원 정보를 찾을 수 없습니다."}, status=400)
    if request.method == 'POST':
        # 탈퇴 시 is_active를 False로 변경
        user.is_active = False
        user.save()
        # 세션 초기화
        request.session.flush()
        return JsonResponse({"status": "success", "message": "회원탈퇴가 완료되었습니다."})
    else:
        return render(request, 'planner/delete_profile.html', {'user': user})


# API 키들 (환경변수나 settings에서 불러오는 것이 좋습니다)
GOOGLE_MAPS_API_KEY = "AIzaSyCrrpnBOa4XrAStl7Uw3AEmWcT2Q-iPJNI"
KTO_API_KEY = "dNeku9S%2F21ZCjP5yrP3nKwrtnJUDORoRqP5quqd7TiiqN8%2B8jsSdT%2BMFp6I40J30euRBeJmDzJ1Qik74yqWH%2BQ%3D%3D"


@csrf_protect
def plan_schedule_view(request):
    """
    일정 만들기/수정 페이지:
      - GET 요청 시:
          * edit_plan 파라미터가 있으면 해당 Planner와 관련 PlannerDetail 데이터를 불러와서
            폼에 미리 채울 데이터를 context에 담아 템플릿으로 전달합니다.
          * 없으면 일반 일정 작성 로직을 수행합니다.
      - POST 요청 시:
          * payload에 edit_plan 값이 있으면 기존 Planner를 업데이트(기존 PlannerDetail 삭제 후 새로 생성)하고,
            그렇지 않으면 새 일정을 생성합니다.
      참고: wdate는 CharField이므로 "YYYY-MM-DD" 형식의 문자열로 저장합니다.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "message": "잘못된 JSON 데이터입니다."}, status=400)

        travel_title = data.get("travel_title")
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        destination = data.get("destination")
        itineraries = data.get("itineraries", {})  # 예: {"1": [ {...}, {...} ], "2": [ ... ], ...}
        edit_plan = data.get("edit_plan")  # 수정 모드일 경우 Planner의 plan_no

        if not all([travel_title, start_date, end_date, destination]):
            return JsonResponse({"status": "error", "message": "필수 필드가 누락되었습니다."}, status=400)

        user_email = request.session.get("user_email")
        if not user_email:
            return JsonResponse({"status": "error", "message": "로그인이 필요합니다."}, status=401)
        try:
            user = Signup.objects.get(email=user_email)
        except Signup.DoesNotExist:
            return JsonResponse({"status": "error", "message": "회원 정보를 찾을 수 없습니다."}, status=400)

        if edit_plan:
            # 수정 모드: 기존 Planner 업데이트
            planner = get_object_or_404(Planner, plan_no=edit_plan)
            planner.region = destination
            planner.sdate = start_date
            planner.edate = end_date
            planner.save()
            # 기존 세부 일정 삭제
            PlannerDetail.objects.filter(planner=planner).delete()
        else:
            # 신규 일정 생성
            planner = Planner.objects.create(
                region=destination,
                plan_img="",
                sdate=start_date,
                edate=end_date
            )

        try:
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            return JsonResponse({"status": "error", "message": "시작일 형식이 올바르지 않습니다."}, status=400)

        # 각 DAY별 PlannerDetail 생성
        for day, items in itineraries.items():
            try:
                day_int = int(day)
            except ValueError:
                continue
            calculated_date = start_date_obj + timedelta(days=day_int - 1)
            wdate_str = calculated_date.strftime("%Y-%m-%d")
            for index, item in enumerate(items, start=1):
                tour_title = item.get("name")
                if not tour_title:
                    continue
                try:
                    tour = Tourlist.objects.get(title=tour_title)
                except Tourlist.DoesNotExist:
                    tour = Tourlist.objects.create(
                        title=tour_title,
                        addr1=item.get("address", ""),
                        areacode=None,
                        sigungucode=None,
                        image2="",
                        readcount=0,
                        ping=0,
                    )
                memo_value = item.get("memo", "")
                # plan_name은 전체 여행 제목만 저장 (수정 시 prefill 용)
                PlannerDetail.objects.create(
                    plan_name=travel_title,
                    planner=planner,
                    signup=user,
                    title=tour,
                    wdate=f"DAY {day}",
                    actual_date=wdate_str,
                    memo=memo_value
                )
        return JsonResponse({"status": "success", "message": "일정이 저장되었습니다."})
    else:
        # GET 요청 처리
        edit_plan = request.GET.get("edit_plan")
        if edit_plan:
            planner = get_object_or_404(Planner, plan_no=edit_plan)
            details = PlannerDetail.objects.filter(planner=planner).order_by('wdate')
            travel_title = details.first().plan_name if details.exists() else planner.region
            itineraries = {}
            if planner.sdate:
                start_date_obj = planner.sdate  # 이미 date 타입입니다.
                for detail in details:
                    if detail.actual_date:  # actual_date 필드 사용
                        day_num = (detail.actual_date - start_date_obj).days + 1
                        itineraries.setdefault(day_num, []).append({
                            "name": detail.title.title,
                            "address": detail.title.addr1,
                            "memo": detail.memo,
                        })
            # 추천 장소 로직 (수정 모드에서는 기존 Planner.region 사용)
            dest = planner.region
            recommended_places = []
            search_lat, search_lng = None, None
            if dest:
                google_url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={dest}&language=ko&key={GOOGLE_MAPS_API_KEY}"
                google_response = requests.get(google_url)
                google_places = google_response.json()
                if "results" in google_places and google_places["results"]:
                    first_place = google_places["results"][0]
                    search_lat = first_place["geometry"]["location"]["lat"]
                    search_lng = first_place["geometry"]["location"]["lng"]
                    for place in google_places["results"]:
                        recommended_places.append({
                            "name": place["name"],
                            "address": place.get("formatted_address", ""),
                            "description": place.get("types", []),
                            "lat": place["geometry"]["location"]["lat"],
                            "lng": place["geometry"]["location"]["lng"],
                        })
                if search_lat and search_lng:
                    nearby_url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={search_lat},{search_lng}&radius=2000&language=ko&key={GOOGLE_MAPS_API_KEY}"
                    nearby_response = requests.get(nearby_url)
                    nearby_places = nearby_response.json()
                    for place in nearby_places.get("results", []):
                        recommended_places.append({
                            "name": place["name"],
                            "address": place.get("vicinity", ""),
                            "description": place.get("types", []),
                            "lat": place["geometry"]["location"]["lat"],
                            "lng": place["geometry"]["location"]["lng"],
                        })
            if search_lat is None or search_lng is None:
                map_center = {"lat": 36.5, "lng": 127.5}
            else:
                map_center = {"lat": search_lat, "lng": search_lng}
            context = {
                "edit_plan": edit_plan,  # 수정 모드에서는 Planner의 plan_no를 전달
                "travel_title": travel_title,
                "start_date": planner.sdate,
                "end_date": planner.edate,
                "destination": planner.region,
                "itineraries": json.dumps(itineraries),
                "recommended_places": recommended_places,
                "recommended_json": json.dumps(recommended_places),
                "google_map_api_key": GOOGLE_MAPS_API_KEY,
                "map_center": map_center,
            }
            return render(request, "planner/plan_schedule.html", context)
        else:
            # 일반 GET 요청: 추천 로직 그대로 수행
            destination = request.GET.get("destination", "")
            recommended_places = []
            search_lat, search_lng = None, None
            if destination:
                google_url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={destination}&language=ko&key={GOOGLE_MAPS_API_KEY}"
                google_response = requests.get(google_url)
                google_places = google_response.json()
                if "results" in google_places and google_places["results"]:
                    first_place = google_places["results"][0]
                    search_lat = first_place["geometry"]["location"]["lat"]
                    search_lng = first_place["geometry"]["location"]["lng"]
                    for place in google_places["results"]:
                        recommended_places.append({
                            "name": place["name"],
                            "address": place.get("formatted_address", ""),
                            "description": place.get("types", []),
                            "lat": place["geometry"]["location"]["lat"],
                            "lng": place["geometry"]["location"]["lng"],
                        })
                if search_lat and search_lng:
                    nearby_url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={search_lat},{search_lng}&radius=2000&language=ko&key={GOOGLE_MAPS_API_KEY}"
                    nearby_response = requests.get(nearby_url)
                    nearby_places = nearby_response.json()
                    for place in nearby_places.get("results", []):
                        recommended_places.append({
                            "name": place["name"],
                            "address": place.get("vicinity", ""),
                            "description": place.get("types", []),
                            "lat": place["geometry"]["location"]["lat"],
                            "lng": place["geometry"]["location"]["lng"],
                        })
                ktour_url = f"http://api.visitkorea.or.kr/openapi/service/rest/KorService/searchKeyword?serviceKey={KTO_API_KEY}&keyword={destination}&numOfRows=20&pageNo=1&MobileOS=ETC&MobileApp=AppTest&_type=json"
                ktour_response = requests.get(ktour_url)
                ktour_places = ktour_response.json()
                items = ktour_places.get("response", {}).get("body", {}).get("items", {}).get("item", [])
                if isinstance(items, dict):
                    items = [items]
                for place in items:
                    recommended_places.append({
                        "name": place.get("title", ""),
                        "address": place.get("addr1", ""),
                        "description": place.get("contenttypeid", "설명 없음"),
                        "lat": place.get("mapx", ""),
                        "lng": place.get("mapy", ""),
                    })
            if search_lat is None or search_lng is None:
                map_center = {"lat": 36.5, "lng": 127.5}
            else:
                map_center = {"lat": search_lat, "lng": search_lng}
            context = {
                "destination": destination,
                "recommended_places": recommended_places,
                "recommended_json": json.dumps(recommended_places),
                "google_map_api_key": GOOGLE_MAPS_API_KEY,
                "map_center": map_center,
            }
            return render(request, 'planner/plan_schedule.html', context)

@csrf_exempt
def save_schedule_view(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "message": "잘못된 JSON 데이터입니다."}, status=400)

        travel_title = data.get("travel_title")
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        destination = data.get("destination")
        itineraries = data.get("itineraries", {})  # 예: {"1": [ {...}, {...} ], "2": [ ... ], ...}

        if not all([travel_title, start_date, end_date, destination]):
            return JsonResponse({"status": "error", "message": "필수 필드가 누락되었습니다."}, status=400)

        user_email = request.session.get("user_email")
        if not user_email:
            return JsonResponse({"status": "error", "message": "로그인이 필요합니다."}, status=401)
        try:
            user = Signup.objects.get(email=user_email)
        except Signup.DoesNotExist:
            return JsonResponse({"status": "error", "message": "회원 정보를 찾을 수 없습니다."}, status=400)

        # 수정 모드 여부 확인 (edit_plan 값이 있으면 기존 일정 업데이트)
        edit_plan = data.get("edit_plan")
        if edit_plan:
            planner = get_object_or_404(Planner, plan_no=edit_plan)
            planner.region = destination
            planner.sdate = start_date
            planner.edate = end_date
            planner.save()
            # 기존 세부 일정 삭제
            PlannerDetail.objects.filter(planner=planner).delete()
        else:
            planner = Planner.objects.create(
                region=destination,
                plan_img="",
                sdate=start_date,
                edate=end_date
            )

        try:
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            return JsonResponse({"status": "error", "message": "시작일 형식이 올바르지 않습니다."}, status=400)

        # 각 DAY별 itinerary 항목에 대해 PlannerDetail 레코드 생성
        for day, items in itineraries.items():
            try:
                day_int = int(day)
            except ValueError:
                continue
            # 실제 날짜 계산: DAY 1은 시작일, DAY 2는 시작일+1일 등
            calculated_date = start_date_obj + timedelta(days=day_int - 1)
            wdate_str = calculated_date.strftime("%Y-%m-%d")  # 실제 날짜 문자열

            for index, item in enumerate(items, start=1):
                tour_title = item.get("name")
                if not tour_title:
                    continue
                try:
                    tour = Tourlist.objects.get(title=tour_title)
                except Tourlist.DoesNotExist:
                    tour = Tourlist.objects.create(
                        title=tour_title,
                        addr1=item.get("address", ""),
                        areacode=None,
                        sigungucode=None,
                        image2="",
                        readcount=0,
                        ping=0,
                    )
                memo_value = item.get("memo", "")
                # 여기서 wdate는 "DAY {day}"로 표시용, actual_date는 실제 날짜를 저장합니다.
                PlannerDetail.objects.create(
                    plan_name=travel_title,
                    planner=planner,
                    signup=user,
                    title=tour,
                    wdate=f"DAY {day}",       # 표시용 텍스트
                    actual_date=wdate_str,     # 실제 날짜 데이터 (YYYY-MM-DD)
                    memo=memo_value
                )
        return JsonResponse({"status": "success", "message": "일정이 저장되었습니다."})
    else:
        return JsonResponse({"status": "error", "message": "POST 요청만 허용됩니다."}, status=405)



@csrf_exempt
def update_destination_view(request):
    """
    AJAX GET 요청으로 전달된 destination을 기반으로,
    Google Places API (Text Search, Nearby Search)와 한국관광공사 API를 사용해
    추천 장소 데이터를 수집하고, 해당 지역의 지도 중심 좌표와 함께 JSON으로 반환합니다.
    """
    destination = request.GET.get("destination", "").strip()

    # 초기값 설정
    recommended_places = []
    search_lat, search_lng = None, None

    if destination:
        # 1. Google Places API - Text Search
        google_url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={destination}&language=ko&key={GOOGLE_MAPS_API_KEY}"
        google_response = requests.get(google_url)
        google_places = google_response.json()
        if "results" in google_places and google_places["results"]:
            first_place = google_places["results"][0]
            search_lat = first_place["geometry"]["location"]["lat"]
            search_lng = first_place["geometry"]["location"]["lng"]
            for place in google_places["results"]:
                recommended_places.append({
                    "name": place["name"],
                    "address": place.get("formatted_address", ""),
                    "description": place.get("types", []),
                    "lat": place["geometry"]["location"]["lat"],
                    "lng": place["geometry"]["location"]["lng"],
                })

        # 2. Google Places API - Nearby Search
        if search_lat and search_lng:
            nearby_url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={search_lat},{search_lng}&radius=2000&language=ko&key={GOOGLE_MAPS_API_KEY}"
            nearby_response = requests.get(nearby_url)
            nearby_places = nearby_response.json()
            for place in nearby_places.get("results", []):
                recommended_places.append({
                    "name": place["name"],
                    "address": place.get("vicinity", ""),
                    "description": place.get("types", []),
                    "lat": place["geometry"]["location"]["lat"],
                    "lng": place["geometry"]["location"]["lng"],
                })

    # 지도 중심 좌표 결정 (Google Places API에서 얻은 좌표가 없으면 기본값 사용)
    if search_lat is None or search_lng is None:
        map_center = {"lat": 36.5, "lng": 127.5}
    else:
        map_center = {"lat": search_lat, "lng": search_lng}

    return JsonResponse({
        "destination": destination,
        "map_center": map_center,
        "recommended_places": recommended_places
    })

@csrf_exempt
def schedule_delete_view(request, plan_no):
    user_email = request.session.get("user_email")
    if not user_email:
        return JsonResponse({"status": "error", "message": "로그인이 필요합니다."}, status=401)
    try:
        planner = Planner.objects.get(plan_no=plan_no)
        if not PlannerDetail.objects.filter(planner=planner, signup__email=user_email).exists():
            return JsonResponse({"status": "error", "message": "삭제 권한이 없습니다."}, status=403)
        planner.delete()
        return JsonResponse({"status": "success", "message": "일정이 삭제되었습니다."})
    except Planner.DoesNotExist:
        return JsonResponse({"status": "error", "message": "일정을 찾을 수 없습니다."}, status=404)


def board_list(request):
    """
    게시판 목록 페이지:
    - 모든 게시글을 최신순으로 보여주고, 페이지네이션 처리합니다.
    - 검색어가 있으면 제목 또는 내용을 기준으로 필터링합니다.
    """
    query = request.GET.get("q", "")
    boards = Board.objects.all().order_by("-created_at")
    if query:
        boards = boards.filter(title__icontains=query) | boards.filter(content__icontains=query)
    paginator = Paginator(boards, 3)  # 페이지당 3개 게시글
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(request, "planner/board_list.html", {"page_obj": page_obj, "query": query})


def board_detail(request, board_id):
    """
    게시글 상세보기 페이지
    """
    board = Board.objects.get(id=board_id)
    return render(request, "planner/board_detail.html", {"board": board})


@csrf_exempt
def board_create(request):
    user_email = request.session.get("user_email")
    if request.method == "POST":
        if not user_email:
            return JsonResponse({"status": "error", "message": "로그인이 필요합니다."}, status=401)
        try:
            author = Signup.objects.get(email=user_email)
        except Signup.DoesNotExist:
            return JsonResponse({"status": "error", "message": "회원 정보를 찾을 수 없습니다."}, status=400)
        title = request.POST.get("title")
        content = request.POST.get("content")
        if not title or not content:
            return JsonResponse({"status": "error", "message": "제목과 내용을 모두 입력해 주세요."}, status=400)
        board = Board.objects.create(
            title=title,
            content=content,
            author=author,
        )
        return JsonResponse({"status": "success", "message": "게시글이 작성되었습니다.", "board_id": board.id})
    else:
        # GET 요청 시, 로그인하지 않은 경우 board_list 페이지로 리다이렉트하며 메시지 전달
        if not user_email:
            messages.error(request, "로그인이 필요합니다.")
            return redirect('board_list')
        # 로그인된 상태라면 작성 페이지 렌더링
        return render(request, "planner/board_create.html")


@csrf_exempt
def board_update(request, board_id):
    """
    게시글 수정 기능
    """
    user_email = request.session.get("user_email")
    if not user_email:
        return JsonResponse({"status": "error", "message": "로그인이 필요합니다."}, status=401)

    board = Board.objects.get(id=board_id)
    if board.author.email != user_email:
        return JsonResponse({"status": "error", "message": "수정 권한이 없습니다."}, status=403)

    if request.method == "POST":
        title = request.POST.get("title")
        content = request.POST.get("content")
        if not title or not content:
            return JsonResponse({"status": "error", "message": "제목과 내용을 모두 입력해 주세요."}, status=400)
        board.title = title
        board.content = content
        board.save()
        return JsonResponse({"status": "success", "message": "게시글이 수정되었습니다."})
    else:
        return render(request, "planner/board_update.html", {"board": board})


@csrf_exempt
def board_delete(request, board_id):
    """
    게시글 삭제 기능
    """
    user_email = request.session.get("user_email")
    if not user_email:
        return JsonResponse({"status": "error", "message": "로그인이 필요합니다."}, status=401)

    board = Board.objects.get(id=board_id)
    if board.author.email != user_email:
        return JsonResponse({"status": "error", "message": "삭제 권한이 없습니다."}, status=403)

    if request.method == "POST":
        board.delete()
        return JsonResponse({"status": "success", "message": "게시글이 삭제되었습니다."})
    else:
        return render(request, "planner/board_delete.html", {"board": board})


@csrf_exempt
def comment_create(request, board_id):
    """
    댓글 작성 뷰:
    - 로그인한 사용자가 게시글(board_id)에 댓글을 작성합니다.
    - AJAX POST 요청으로 댓글 내용을 받아 저장합니다.
    """
    user_email = request.session.get("user_email")
    if not user_email:
        return JsonResponse({"status": "error", "message": "로그인이 필요합니다."}, status=401)

    try:
        author = Signup.objects.get(email=user_email)
    except Signup.DoesNotExist:
        return JsonResponse({"status": "error", "message": "회원 정보를 찾을 수 없습니다."}, status=400)

    try:
        board = Board.objects.get(id=board_id)
    except Board.DoesNotExist:
        return JsonResponse({"status": "error", "message": "게시글을 찾을 수 없습니다."}, status=404)

    if request.method == "POST":
        content = request.POST.get("content")
        if not content:
            return JsonResponse({"status": "error", "message": "댓글 내용을 입력해 주세요."}, status=400)

        comment = Comment.objects.create(
            board=board,
            author=author,
            content=content
        )

        return JsonResponse({
            "status": "success",
            "message": "댓글이 작성되었습니다.",
            "comment": {
                "id": comment.id,
                "author": comment.author.name,
                "content": comment.content,
                "created_at": comment.created_at.strftime("%Y-%m-%d %H:%M")
            }
        })
    else:
        return JsonResponse({"status": "error", "message": "POST 요청만 허용됩니다."}, status=405)


@csrf_exempt
def comment_delete(request, comment_id):
    """
    댓글 삭제 뷰:
    - 로그인한 사용자가 자신의 댓글(comment_id)을 삭제합니다.
    """
    user_email = request.session.get("user_email")
    if not user_email:
        return JsonResponse({"status": "error", "message": "로그인이 필요합니다."}, status=401)

    try:
        comment = Comment.objects.get(id=comment_id)
    except Comment.DoesNotExist:
        return JsonResponse({"status": "error", "message": "댓글을 찾을 수 없습니다."}, status=404)

    # 댓글 작성자 본인인지 확인
    if comment.author.email != user_email:
        return JsonResponse({"status": "error", "message": "삭제 권한이 없습니다."}, status=403)

    if request.method == "POST":
        comment.delete()
        return JsonResponse({"status": "success", "message": "댓글이 삭제되었습니다."})
    else:
        return JsonResponse({"status": "error", "message": "POST 요청만 허용됩니다."}, status=405)

@csrf_exempt
def comment_update(request, comment_id):
    """
    댓글 수정 뷰:
    - 로그인한 사용자가 자신의 댓글(comment_id)을 수정합니다.
    - POST 요청으로 수정할 댓글 내용을 받아 업데이트합니다.
    """
    user_email = request.session.get("user_email")
    if not user_email:
        return JsonResponse({"status": "error", "message": "로그인이 필요합니다."}, status=401)

    try:
        comment = Comment.objects.get(id=comment_id)
    except Comment.DoesNotExist:
        return JsonResponse({"status": "error", "message": "댓글을 찾을 수 없습니다."}, status=404)

    # 댓글 작성자 확인
    if comment.author.email != user_email:
        return JsonResponse({"status": "error", "message": "수정 권한이 없습니다."}, status=403)

    if request.method == "POST":
        new_content = request.POST.get("content")
        if not new_content:
            return JsonResponse({"status": "error", "message": "수정할 내용을 입력해 주세요."}, status=400)
        comment.content = new_content
        comment.save()
        return JsonResponse({
            "status": "success",
            "message": "댓글이 수정되었습니다.",
            "comment": {
                "id": comment.id,
                "author": comment.author.name,
                "content": comment.content,
                "created_at": comment.created_at.strftime("%Y-%m-%d %H:%M")
            }
        })
    else:
        return JsonResponse({"status": "error", "message": "POST 요청만 허용됩니다."}, status=405)

