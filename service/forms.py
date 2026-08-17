from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from .auth import MANAGER_GROUP, MECHANIC_GROUP
from .models import EstimateItem, Order, Service
from .policies import allowed_transitions
from .validators import normalize_phone, normalize_plate, validate_requested_datetime, validate_vin


class MultipleInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        if not data:
            return []
        values = data if isinstance(data, (list, tuple)) else [data]
        return [super(MultipleFileField, self).clean(item, initial) for item in values]


class AccessibleFormMixin:
    def full_clean(self):
        super().full_clean()
        for name, field in self.fields.items():
            if name in self.errors:
                field.widget.attrs["aria-invalid"] = "true"
                field.widget.attrs["aria-describedby"] = f"error-{self.add_prefix(name)}"


class BookingForm(AccessibleFormMixin, forms.Form):
    name = forms.CharField(max_length=120, label="Имя")
    phone = forms.CharField(max_length=30, label="Телефон")
    email = forms.EmailField(required=False, label="Email")
    make = forms.CharField(max_length=60, label="Марка")
    model = forms.CharField(max_length=60, label="Модель")
    year = forms.IntegerField(required=False, min_value=1950, label="Год")
    plate = forms.CharField(required=False, max_length=20, label="Госномер")
    vin = forms.CharField(required=False, max_length=17, label="VIN")
    service = forms.ModelChoiceField(queryset=Service.objects.filter(is_active=True), label="Услуга")
    desired_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), label="Желаемая дата")
    desired_time = forms.TimeField(
        required=False, widget=forms.TimeInput(attrs={"type": "time"}), label="Желаемое время"
    )
    problem = forms.CharField(
        max_length=3000, widget=forms.Textarea(attrs={"rows": 4}), label="Описание проблемы"
    )
    photos = MultipleFileField(
        required=False,
        widget=MultipleInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
        label="Фотографии",
    )
    consent = forms.BooleanField(label="Согласен с обработкой персональных данных")
    website = forms.CharField(required=False, widget=forms.HiddenInput)
    submission_key = forms.CharField(widget=forms.HiddenInput)

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])

    def clean_email(self):
        return self.cleaned_data.get("email", "").strip().lower()

    def clean_plate(self):
        return normalize_plate(self.cleaned_data.get("plate", ""))

    def clean_vin(self):
        return validate_vin(self.cleaned_data.get("vin", ""))

    def clean_year(self):
        year = self.cleaned_data.get("year")
        if year and year > timezone.localdate().year + 1:
            raise ValidationError("Некорректный год автомобиля.")
        return year

    def clean(self):
        data = super().clean()
        if data.get("website"):
            raise ValidationError("Заявка отклонена.")
        if data.get("desired_date"):
            validate_requested_datetime(data["desired_date"], data.get("desired_time"))
        return data


class StatusForm(forms.Form):
    status = forms.ChoiceField(label="Следующий статус")
    expected_status = forms.CharField(widget=forms.HiddenInput)
    public_message = forms.CharField(
        max_length=500, required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Сообщение клиенту"
    )
    internal_message = forms.CharField(
        max_length=1000, required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Внутренняя причина"
    )

    def __init__(self, *args, order=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = dict(Order.Status.choices)
        self.fields["status"].choices = (
            [(value, choices[value]) for value in sorted(allowed_transitions(user, order))]
            if order and user
            else []
        )
        if order:
            self.fields["expected_status"].initial = order.status


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["assigned_to"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user_model = get_user_model()
        self.fields["assigned_to"].queryset = (
            user_model.objects.filter(is_active=True, groups__name__in=[MANAGER_GROUP, MECHANIC_GROUP])
            .distinct()
            .order_by("username")
        )


class ScheduleForm(forms.ModelForm):
    reason = forms.CharField(
        max_length=500, required=False, label="Причина переноса", widget=forms.Textarea(attrs={"rows": 2})
    )

    class Meta:
        model = Order
        fields = ["confirmed_start_at", "confirmed_end_at"]
        widgets = {
            "confirmed_start_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "confirmed_end_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def clean(self):
        data = super().clean()
        start, end = data.get("confirmed_start_at"), data.get("confirmed_end_at")
        if start and timezone.is_naive(start):
            self.add_error("confirmed_start_at", "Укажите время с учётом часового пояса.")
        if end and timezone.is_naive(end):
            self.add_error("confirmed_end_at", "Укажите время с учётом часового пояса.")
        if start and start < timezone.now():
            self.add_error("confirmed_start_at", "Подтверждённое время не может быть в прошлом.")
        if start and end and end <= start:
            self.add_error("confirmed_end_at", "Окончание должно быть позже начала.")
        return data


class PriceForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["estimate", "estimate_note", "final_price"]


class ManualApprovalForm(forms.Form):
    version = forms.IntegerField(widget=forms.HiddenInput)
    method = forms.ChoiceField(
        choices=[("phone", "Телефон"), ("in_person", "Лично"), ("email", "Email")], label="Метод"
    )
    note = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 2}), label="Примечание")


class EstimateItemForm(forms.ModelForm):
    class Meta:
        model = EstimateItem
        fields = ["item_type", "name", "quantity", "unit_price", "order_index"]


class CommentForm(forms.Form):
    text = forms.CharField(
        max_length=2000, strip=True, widget=forms.Textarea(attrs={"rows": 3}), label="Комментарий"
    )
