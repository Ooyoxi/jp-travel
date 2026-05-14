from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.utils.translation import gettext as _


def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, _("注册成功！"))
            return redirect("notes:home")
    else:
        form = UserCreationForm()
    return render(request, "registration/register.html", {"form": form})
