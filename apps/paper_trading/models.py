from django.conf import settings
from django.db import models
class PaperAccount(models.Model):
    user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='paper_account')
    balance=models.DecimalField(max_digits=18,decimal_places=8,default=100000); equity=models.DecimalField(max_digits=18,decimal_places=8,default=100000)
    margin=models.DecimalField(max_digits=18,decimal_places=8,default=0); free_margin=models.DecimalField(max_digits=18,decimal_places=8,default=100000)
    currency=models.CharField(max_length=8,default='USD'); limits=models.JSONField(default=dict,blank=True); created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
class PaperTrade(models.Model):
    paper_account=models.ForeignKey(PaperAccount,on_delete=models.CASCADE,related_name='trades')
    strategy=models.CharField(max_length=160); symbol=models.CharField(max_length=40,db_index=True)
    entry=models.DecimalField(max_digits=20,decimal_places=8); exit=models.DecimalField(max_digits=20,decimal_places=8,null=True,blank=True); profit=models.DecimalField(max_digits=18,decimal_places=8,default=0)
    status=models.CharField(max_length=24,default='open',db_index=True); execution_payload=models.JSONField(default=dict,blank=True); created_at=models.DateTimeField(auto_now_add=True); closed_at=models.DateTimeField(null=True,blank=True)
