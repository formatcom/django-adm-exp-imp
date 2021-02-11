from django.contrib.auth.models import User
from django.db import models


class UserMetaData(models.Model):

    key = models.CharField(max_length=256)
    value = models.CharField(max_length=256)

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):

        if not getattr(self, "user", None):
            return super().__str__();

        return '{}: {}={}'.format(
                                    self.user,
                                    self.key,
                                    self.value)

    class Meta:
        unique_together = ['key', 'user']
