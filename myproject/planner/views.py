import json
import re
import random
import string
import requests # 실제 API 호출 시 사용
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from .models import Signup, Planner, Tourlist, PlannerDetail, Board, Comment
from django.core.mail import send_mail  # 실제 메일 전송 시 사용 (설정 필요)

def main_page(request):
    """
    메인 페이지: 캐러셀, 배너, 검색 등 기능을 포함합니다.
    """
    return render(request, 'planner/main_page.html')

def signup_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        name = request.POST.get('name')
        birth = request.POST.get('birth')
        addr = request.POST.get('addr')
        phone_num = request.POST.get('phone_num')

        # 이메일 유효성 검사 (간단한 정규 표현식)
        email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not re.match(email_pattern, email):
            return JsonResponse({'status': 'error', 'message': '유효하지 않은 이메일 형식입니다.'}, status=400)

        # 비밀번호 유효성 검사 (예: 최소 6자 이상)
        if len(password) < 6:
            return JsonResponse({'status': 'error', 'message': '비밀번호는 6자 이상이어야 합니다.'}, status=400)

        # 이미 가입된 이메일인지 확인
        if Signup.objects.filter(email=email).exists():
            return JsonResponse({'status': 'error', 'message': '이미 가입된 이메일입니다.'}, status=400)

        # 회원 생성 (birth는 값이 없으면 None 처리)
        Signup.objects.create(
            email=email,
            password=password,
            name=name,
            birth=birth if birth else None,
            addr=addr,
            phone_num=phone_num
        )

        return JsonResponse({'status': 'success', 'message': '회원가입 성공'})
    else:
        # GET 요청 시 회원가입 페이지 렌더링
        return render(request, 'planner/signup.html')

@csrf_exempt  # 개발 단계에서 CSRF 보호를 임시 비활성화 (실제 배포시에는 CSRF 보호를 활성화해야 합니다)
def login_view(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        try:
            user = Signup.objects.get(email=email, password=password)
            # 로그인 성공 시 세션에 회원 정보 저장
            request.session["user_email"] = user.email
            request.session["user_name"] = user.name
            return JsonResponse({"status": "success", "user_name": user.name})
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
    POST 요청으로 이메일과 이름을 받아 회원 정보를 확인하고,
    임시 비밀번호를 생성하여 회원의 비밀번호를 업데이트합니다.
    (실제 운영 시, 임시 비밀번호를 이메일로 전송하도록 구현)
    """
    if request.method == "POST":
        email = request.POST.get("email")
        name = request.POST.get("name")
        try:
            user = Signup.objects.get(email=email, name=name)
        except Signup.DoesNotExist:
            return JsonResponse({
                "status": "error",
                "message": "해당 회원 정보를 찾을 수 없습니다."
            }, status=400)

        # 임시 비밀번호 생성 (8자리)
        temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))

        # 임시 비밀번호로 업데이트 (실제 환경에서는 비밀번호 암호화 필요)
        user.password = temp_password
        user.save()

        # 실제 메일 전송 코드 (메일 설정 완료 시 사용)
        # send_mail(
        #     subject="여행 플래너 임시 비밀번호",
        #     message=f"임시 비밀번호는 {temp_password}입니다. 로그인 후 반드시 비밀번호를 변경해주세요.",
        #     from_email="no-reply@yourdomain.com",
        #     recipient_list=[email],
        #     fail_silently=False,
        # )

        # 테스트용: 임시 비밀번호를 JSON 응답으로 반환 (실제 운영 시에는 반환하지 않음)
        return JsonResponse({
            "status": "success",
            "message": f"임시 비밀번호가 {temp_password}로 설정되었습니다. 이메일을 확인하세요."
        })
    else:
        # GET 요청 시 비밀번호 찾기 페이지 렌더링
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
    마이페이지: 로그인한 사용자의 회원정보와 '나의 일정' (추후 구현 예정)을 표시합니다.
    """
    user_email = request.session.get('user_email')
    if not user_email:
        return redirect('login')
    try:
        user = Signup.objects.get(email=user_email)
    except Signup.DoesNotExist:
        return redirect('login')
    return render(request, 'planner/my_page.html', {'user': user})

@csrf_exempt
def update_profile_view(request):
    """
    회원정보 수정: POST 요청으로 수정된 데이터를 받아 회원 정보를 업데이트합니다.
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
        user.save()
        return JsonResponse({"status": "success", "message": "회원정보가 업데이트 되었습니다."})
    else:
        return render(request, 'planner/update_profile.html', {'user': user})

@csrf_exempt
def delete_profile_view(request):
    """
    회원탈퇴: POST 요청 시 현재 회원 정보를 삭제합니다.
    """
    user_email = request.session.get('user_email')
    if not user_email:
        return JsonResponse({"status": "error", "message": "로그인이 필요합니다."}, status=401)
    try:
        user = Signup.objects.get(email=user_email)
    except Signup.DoesNotExist:
        return JsonResponse({"status": "error", "message": "회원 정보를 찾을 수 없습니다."}, status=400)
    if request.method == 'POST':
        user.delete()
        request.session.flush()  # 세션 초기화
        return JsonResponse({"status": "success", "message": "회원탈퇴가 완료되었습니다."})
    else:
        return render(request, 'planner/delete_profile.html', {'user': user})


@csrf_exempt
def plan_schedule_view(request):
    """
    일정 만들기 페이지:
    - GET 요청 시: 여행지명(destination)을 GET 파라미터로 받아 추천 장소 정보를 표시합니다.
      (추천 장소 정보에 위도/경도 값을 포함하여 지도에 마커 표시)
    - POST 요청 시: 현재 로그인한 사용자의 일정 작성 폼 데이터를 받아 새로운 Planner와 PlannerDetail 레코드를 생성합니다.
    """
    if request.method == "POST":
        # 반드시 로그인 상태여야 함
        user_email = request.session.get("user_email")
        if not user_email:
            return JsonResponse({"status": "error", "message": "로그인이 필요합니다."}, status=401)
        try:
            user = Signup.objects.get(email=user_email)
        except Signup.DoesNotExist:
            return JsonResponse({"status": "error", "message": "회원 정보를 찾을 수 없습니다."}, status=400)

        # 폼 데이터 추출
        plan_title = request.POST.get("plan_title")
        plan_memo = request.POST.get("plan_memo")
        destination = request.POST.get("destination")
        tour_title = request.POST.get("tour_title")

        if not all([plan_title, destination, tour_title]):
            return JsonResponse({"status": "error", "message": "필수 필드가 누락되었습니다."}, status=400)

        # 새로운 Planner 레코드 생성 (여행 일정의 기본 정보)
        new_planner = Planner.objects.create(
            region=destination,
            plan_img="",
            sdate=None,
            edate=None,
        )

        # TOURLIST에서 tour_title에 해당하는 레코드 검색, 없으면 새로 생성
        try:
            tour = Tourlist.objects.get(title=tour_title)
        except Tourlist.DoesNotExist:
            tour = Tourlist.objects.create(
                title=tour_title,
                addr1="",
                areacode=None,
                sigungucode=None,
                image2="",
                readcount=0,
                ping=0,
            )

        # 새로운 PlannerDetail 레코드 생성 (상세 일정)
        new_detail = PlannerDetail.objects.create(
            plan_name=plan_title,  # PK: 일정 제목
            planner=new_planner,
            signup=user,
            title=tour,
            wdate=None,  # 필요에 따라 현재 날짜로 설정 가능
            memo=plan_memo,
        )

        return JsonResponse({"status": "success", "message": "일정이 저장되었습니다."})
    else:  # GET 요청 처리
        destination = request.GET.get("destination", "")
        recommended_places = []
        if destination:
            # 더미 데이터 (위도, 경도 추가)
            recommended_places = [
                {"name": "관광지 A", "address": "주소 A", "description": "멋진 풍경을 감상할 수 있는 명소입니다.", "lat": 33.3617, "lng": 126.5297},
                {"name": "관광지 B", "address": "주소 B", "description": "역사와 문화가 살아있는 장소입니다.", "lat": 33.3644, "lng": 126.5359},
                {"name": "관광지 C", "address": "주소 C", "description": "자연과 함께 힐링할 수 있는 곳입니다.", "lat": 33.3700, "lng": 126.5400},
            ]
        context = {
            "destination": destination,
            "recommended_places": recommended_places,
            # JSON 문자열로 직렬화하여 전달
            "recommended_json": json.dumps(recommended_places),
            "google_map_api_key": "AIzaSyCrrpnBOa4XrAStl7Uw3AEmWcT2Q-iPJNI",
        }
        return render(request, 'planner/plan_schedule.html', context)


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
    paginator = Paginator(boards, 10)  # 페이지당 10개 게시글
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
    """
    게시글 작성 기능 (로그인 필요)
    AJAX POST 요청을 받아 새 게시글을 생성합니다.
    """
    user_email = request.session.get("user_email")
    if not user_email:
        return JsonResponse({"status": "error", "message": "로그인이 필요합니다."}, status=401)
    try:
        author = Signup.objects.get(email=user_email)
    except Signup.DoesNotExist:
        return JsonResponse({"status": "error", "message": "회원 정보를 찾을 수 없습니다."}, status=400)

    if request.method == "POST":
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
        # GET 요청: 게시글 작성 폼 렌더링
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