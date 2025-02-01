"""
Views module for file upload demonstration.
Compatible with Django 4.2.
"""

from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django import forms


class UploadFileForm(forms.Form):
    foo = forms.FileField()


@csrf_exempt
def upload_file(request: HttpRequest) -> HttpResponse:
    """
    Example view for handling file uploads.

    Expects:
    - 'foo' as a FileField in the form
    - 'field1' as a POST parameter
    """
    if request.method == "POST":
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            file_content = form.cleaned_data["foo"].read()
            field1_value = request.POST.get("field1", "")
            response_data = file_content + b"-" + field1_value.encode()
            return HttpResponse(content=response_data)

        # If the form is not valid, return the errors for debug
        return HttpResponse(content=form.errors, status=400)

    # If not a POST request, return a simple response
    return HttpResponse(content="Request method not allowed.", status=405)
