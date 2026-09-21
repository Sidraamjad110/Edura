from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from MediProAPI.apps.users.models import Client
from .models import ClientCredential
from .serializers import ClientCredentialSerializer


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_admin(request):
    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "Admin access required.",
        }, status=status.HTTP_403_FORBIDDEN)
    return None


def _get_client_for_user(user):
    """
    Client.auth_user has related_name='client_profile'
    so the reverse accessor on User is user.client_profile.
    """
    return getattr(user, "client_profile", None)


def _credential_payload(client, row):
    stored = ClientCredentialSerializer(row).data if row else None
    return {
        "client_id": client.id,
        "client_name": client.auth_user.get_full_name() or client.auth_user.username,
        "company_name": client.company_name,
        "configured": row is not None,
        "stored": stored,
    }


# ── Admin views ───────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_credential_list_api(request):
    denied = _require_admin(request)
    if denied:
        return denied

    clients = Client.objects.select_related("auth_user").order_by("id")
    data = []
    for client in clients:
        row = ClientCredential.objects.filter(client_id=client.id).first()
        data.append({
            "client_id": client.id,
            "client_name": client.auth_user.get_full_name() or client.auth_user.username,
            "company_name": client.company_name,
            "configured": row is not None,
        })

    return Response({
        "success": True,
        "message": "Client credentials list retrieved.",
        "data": data,
    })


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def admin_credential_detail_api(request, client_id):
    denied = _require_admin(request)
    if denied:
        return denied

    client = Client.objects.select_related("auth_user").filter(pk=client_id).first()
    if not client:
        return Response({
            "success": False,
            "message": "Client not found.",
        }, status=status.HTTP_404_NOT_FOUND)

    row = ClientCredential.objects.filter(client_id=client_id).first()

    if request.method == "GET":
        return Response({
            "success": True,
            "message": "Client credentials retrieved.",
            "data": _credential_payload(client, row),
        })

    # PATCH — create if not exists, update if exists
    # NOTE: client is read_only in the serializer so we pass it
    # directly to save() — never via the payload
    payload = dict(request.data or {})
    payload.pop("client", None)  # strip if frontend accidentally sends it

    if row:
        serializer = ClientCredentialSerializer(row, data=payload, partial=True)
        if not serializer.is_valid():
            return Response({
                "success": False,
                "message": "Validation failed.",
                "errors": serializer.errors,
            }, status=status.HTTP_400_BAD_REQUEST)
        saved = serializer.save(updated_by=request.user)
    else:
        serializer = ClientCredentialSerializer(data=payload)
        if not serializer.is_valid():
            return Response({
                "success": False,
                "message": "Validation failed.",
                "errors": serializer.errors,
            }, status=status.HTTP_400_BAD_REQUEST)
        # Pass client instance directly to save() — bypasses read_only restriction
        saved = serializer.save(client=client, updated_by=request.user)

    return Response({
        "success": True,
        "message": "Client credentials saved.",
        "data": _credential_payload(client, saved),
    })


# ── Client (self) views ───────────────────────────────────────────────────────

@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def client_credential_api(request):
    client = _get_client_for_user(request.user)
    if not client:
        return Response({
            "success": False,
            "message": "No client profile linked to this account.",
        }, status=status.HTTP_404_NOT_FOUND)

    row = ClientCredential.objects.filter(client=client).first()

    if request.method == "GET":
        return Response({
            "success": True,
            "message": "Credentials retrieved." if row else "No credentials saved yet.",
            "data": _credential_payload(client, row),
        })

    # PATCH — create if not exists, update if exists
    payload = dict(request.data or {})
    payload.pop("client", None)  # strip if accidentally sent

    if row:
        serializer = ClientCredentialSerializer(row, data=payload, partial=True)
        if not serializer.is_valid():
            return Response({
                "success": False,
                "message": "Validation failed.",
                "errors": serializer.errors,
            }, status=status.HTTP_400_BAD_REQUEST)
        saved = serializer.save(updated_by=request.user)
    else:
        serializer = ClientCredentialSerializer(data=payload)
        if not serializer.is_valid():
            return Response({
                "success": False,
                "message": "Validation failed.",
                "errors": serializer.errors,
            }, status=status.HTTP_400_BAD_REQUEST)
        # Pass client instance directly to save() — bypasses read_only restriction
        saved = serializer.save(client=client, updated_by=request.user)

    return Response({
        "success": True,
        "message": "Credentials saved.",
        "data": _credential_payload(client, saved),
    })