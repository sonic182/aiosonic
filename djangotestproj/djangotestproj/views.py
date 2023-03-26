"""Views."""

from django.http import HttpRequest
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from django import forms


class UploadFileForm(forms.Form):
    foo = forms.FileField()


@csrf_exempt
def upload_file(request: HttpRequest):
    """Sample upload file."""
    if request.method == "POST":
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            return HttpResponse(
                content=form.cleaned_data["foo"].read()
                + b"-"
                + request.POST["field1"].encode()
            )
        return HttpResponse(content=form.errors)
    return HttpResponse(content="ko")
