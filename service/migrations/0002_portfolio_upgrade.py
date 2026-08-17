import re
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion

def parse_minutes(value):
    text=(value or "").strip().lower()
    hours=re.search(r"(\d+(?:[.,]\d+)?)\s*(?:ч|час|год)",text)
    minutes=re.search(r"(\d+)\s*(?:мин|хв)",text)
    total=0
    if hours: total+=int(float(hours.group(1).replace(",","."))*60)
    if minutes: total+=int(minutes.group(1))
    if not total:
        number=re.search(r"\d+",text); total=int(number.group()) if number else 60
    return max(1,min(total,1440))
def migrate_duration(apps,schema_editor):
    Service=apps.get_model("service","Service")
    for item in Service.objects.all().iterator():item.duration_minutes=parse_minutes(item.duration_legacy);item.save(update_fields=["duration_minutes"])
def consolidate_settings(apps,schema_editor):
    Model=apps.get_model("service","SiteSettings");rows=list(Model.objects.order_by("pk"))
    if not rows:return
    keep=rows[0];Model.objects.exclude(pk=keep.pk).delete();keep.singleton=1;keep.save(update_fields=["singleton"])
def normalize_phone(value):
    digits=re.sub(r"\D","",value or "")
    if len(digits)==10 and digits.startswith("0"):digits="38"+digits
    if len(digits)==12 and digits.startswith("380"):return "+"+digits
    return "+"+digits if digits else "unknown"
def merge_customers(apps,schema_editor):
    Customer=apps.get_model("service","Customer");Vehicle=apps.get_model("service","Vehicle");Order=apps.get_model("service","Order")
    masters={}
    for customer in Customer.objects.order_by("pk").iterator():
        phone=normalize_phone(customer.phone);master=masters.get(phone)
        if master is None:customer.phone=phone;customer.save(update_fields=["phone"]);masters[phone]=customer;continue
        Order.objects.filter(customer_id=customer.pk).update(customer_id=master.pk)
        for vehicle in Vehicle.objects.filter(customer_id=customer.pk):
            match=None
            if vehicle.vin:match=Vehicle.objects.filter(customer_id=master.pk,vin=vehicle.vin).first()
            if not match and vehicle.plate:match=Vehicle.objects.filter(customer_id=master.pk,plate=vehicle.plate).first()
            if match:Order.objects.filter(vehicle_id=vehicle.pk).update(vehicle_id=match.pk);vehicle.delete()
            else:vehicle.customer_id=master.pk;vehicle.save(update_fields=["customer"])
        customer.delete()
def snapshot_orders(apps,schema_editor):
    Order=apps.get_model("service","Order")
    for order in Order.objects.select_related("service").all().iterator():order.service_name=order.service.name;order.service_price_from=order.service.price_from;order.save(update_fields=["service_name","service_price_from"])
def transfer_history(apps,schema_editor):
    History=apps.get_model("service","StatusHistory");Event=apps.get_model("service","OrderEvent")
    batch=[]
    for row in History.objects.all().iterator():batch.append(Event(order_id=row.order_id,kind="status",new_status=row.status,public_message=row.message,actor_id=row.created_by_id,created_at=row.created_at))
    if batch:Event.objects.bulk_create(batch)

class Migration(migrations.Migration):
    dependencies=[("service","0001_initial"),migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
        migrations.AddField("sitesettings","singleton",models.PositiveSmallIntegerField(blank=True,null=True,editable=False)),
        migrations.AddField("sitesettings","about",models.TextField(default="Независимый автосервис с прозрачным процессом обработки заявок.")),
        migrations.RemoveField("sitesettings","telegram"),migrations.RunPython(consolidate_settings,migrations.RunPython.noop),
        migrations.AlterField("sitesettings","singleton",models.PositiveSmallIntegerField(default=1,editable=False,unique=True)),
        migrations.RenameField("service","duration","duration_legacy"),migrations.AddField("service","duration_minutes",models.PositiveSmallIntegerField(blank=True,null=True)),migrations.RunPython(migrate_duration,migrations.RunPython.noop),migrations.RemoveField("service","duration_legacy"),migrations.AlterField("service","duration_minutes",models.PositiveSmallIntegerField(default=60)),
        migrations.AlterField("service","description",models.TextField(max_length=1500)),migrations.AlterField("service","price_from",models.DecimalField(decimal_places=2,max_digits=10,validators=[MinValueValidator(Decimal("0"))],verbose_name="Цена от")),
        migrations.AddField("customer","is_demo",models.BooleanField(default=False)),migrations.RunPython(merge_customers,migrations.RunPython.noop),migrations.AlterField("customer","phone",models.CharField(db_index=True,max_length=20,unique=True)),
        migrations.AlterField("vehicle","make",models.CharField(max_length=60)),migrations.AlterField("vehicle","model",models.CharField(max_length=60)),migrations.AlterField("vehicle","vin",models.CharField(blank=True,db_index=True,max_length=17)),migrations.AddConstraint("vehicle",models.UniqueConstraint(condition=~models.Q(plate=""),fields=("customer","plate"),name="unique_customer_plate")),migrations.AddConstraint("vehicle",models.UniqueConstraint(condition=~models.Q(vin=""),fields=("customer","vin"),name="unique_customer_vin")),
        migrations.AddField("order","service_name",models.CharField(default="Услуга",max_length=120)),migrations.AddField("order","service_price_from",models.DecimalField(default=0,decimal_places=2,max_digits=10,validators=[MinValueValidator(Decimal("0"))])),migrations.RunPython(snapshot_orders,migrations.RunPython.noop),
        migrations.AddField("order","confirmed_at",models.DateTimeField(blank=True,null=True)),migrations.AddField("order","estimate_note",models.CharField(blank=True,max_length=500)),migrations.AddField("order","estimate_approved",models.BooleanField(default=False)),migrations.AddField("order","is_demo",models.BooleanField(default=False)),
        migrations.AlterField("order","number",models.CharField(editable=False,max_length=20,unique=True)),migrations.AlterField("order","problem",models.TextField(max_length=3000)),migrations.AlterField("order","status",models.CharField(choices=[("new","Новая заявка"),("pending","Ожидает подтверждения"),("booked","Запись подтверждена"),("accepted","Автомобиль принят"),("diagnostics","Диагностика"),("awaiting_approval","Ожидает согласования"),("parts","Ожидаются запчасти"),("repair","Ремонт"),("ready","Готов к выдаче"),("done","Завершён"),("canceled","Отменён"),("no_show","Клиент не приехал")],db_index=True,default="new",max_length=24)),migrations.AlterField("order","estimate",models.DecimalField(blank=True,decimal_places=2,max_digits=10,null=True,validators=[MinValueValidator(Decimal("0"))])),migrations.AlterField("order","final_price",models.DecimalField(blank=True,decimal_places=2,max_digits=10,null=True,validators=[MinValueValidator(Decimal("0"))])),migrations.AlterField("order","internal_notes",models.TextField(blank=True,max_length=3000)),migrations.AlterField("order","assigned_to",models.ForeignKey(blank=True,limit_choices_to={"is_active":True,"is_staff":True},null=True,on_delete=django.db.models.deletion.SET_NULL,related_name="assigned_orders",to=settings.AUTH_USER_MODEL)),migrations.AddIndex("order",models.Index(fields=["assigned_to","status"],name="service_ord_assigne_58a316_idx")),
        migrations.AddField("orderphoto","original_name",models.CharField(default="photo",max_length=120)),migrations.AddField("orderphoto","content_type",models.CharField(default="image/jpeg",max_length=20)),migrations.AddField("orderphoto","size",models.PositiveIntegerField(default=0)),migrations.AlterField("orderphoto","image",models.ImageField(upload_to="orders/private/")),
        migrations.CreateModel(name="ClientAccess",fields=[("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("token_hash",models.CharField(max_length=64,unique=True)),("expires_at",models.DateTimeField(db_index=True)),("revoked_at",models.DateTimeField(blank=True,null=True)),("created_at",models.DateTimeField(auto_now_add=True)),("created_by",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,to=settings.AUTH_USER_MODEL)),("order",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="access_links",to="service.order"))]),
        migrations.CreateModel(name="OrderEvent",fields=[("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("kind",models.CharField(choices=[("created","Создание"),("status","Статус"),("assignment","Назначение"),("price","Стоимость"),("schedule","Дата"),("link","Клиентская ссылка"),("note","Комментарий")],max_length=20)),("old_status",models.CharField(blank=True,max_length=24)),("new_status",models.CharField(blank=True,max_length=24)),("public_message",models.CharField(blank=True,max_length=500)),("internal_message",models.CharField(blank=True,max_length=1000)),("created_at",models.DateTimeField(auto_now_add=True)),("actor",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,to=settings.AUTH_USER_MODEL)),("order",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="events",to="service.order"))],options={"ordering":["created_at"]}),
        migrations.RunPython(transfer_history,migrations.RunPython.noop),migrations.DeleteModel("StatusHistory"),
        migrations.CreateModel(name="EstimateItem",fields=[("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("name",models.CharField(max_length=160)),("item_type",models.CharField(choices=[("work","Работа"),("part","Деталь")],max_length=8)),("quantity",models.DecimalField(decimal_places=2,default=1,max_digits=8,validators=[MinValueValidator(Decimal("0.01"))])),("unit_price",models.DecimalField(decimal_places=2,max_digits=10,validators=[MinValueValidator(Decimal("0"))])),("order_index",models.PositiveSmallIntegerField(default=0)),("order",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="estimate_items",to="service.order"))],options={"ordering":["order_index","id"]}),
        migrations.CreateModel(name="NotificationLog",fields=[("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("channel",models.CharField(choices=[("email","Email"),("telegram","Telegram")],max_length=12)),("event_type",models.CharField(max_length=40)),("recipient_hint",models.CharField(blank=True,max_length=100)),("status",models.CharField(choices=[("pending","Ожидает"),("sent","Отправлено"),("failed","Ошибка")],default="pending",max_length=12)),("attempts",models.PositiveSmallIntegerField(default=0)),("last_error",models.CharField(blank=True,max_length=300)),("dedupe_key",models.CharField(max_length=120,unique=True)),("created_at",models.DateTimeField(auto_now_add=True)),("sent_at",models.DateTimeField(blank=True,null=True)),("order",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="notifications",to="service.order"))]),
        migrations.CreateModel(name="Submission",fields=[("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("key_hash",models.CharField(max_length=64,unique=True)),("created_at",models.DateTimeField(auto_now_add=True)),("order",models.OneToOneField(blank=True,null=True,on_delete=django.db.models.deletion.CASCADE,to="service.order"))]),
        migrations.AlterField("ordercomment","author",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL)),migrations.AlterField("ordercomment","text",models.TextField(max_length=2000)),
    ]
