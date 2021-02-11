from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as UAdmin
from django.utils.translation import gettext_lazy as _
from django.utils.encoding import force_str
from django.template.response import TemplateResponse
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse

from import_export import resources
from import_export.formats import base_formats
from import_export.admin import ImportExportActionModelAdmin
from import_export.admin import ImportExportModelAdmin
from import_export.fields import Field

from app.models import UserMetaData

@admin.register(UserMetaData)
class UserMetaDataAdmin(admin.ModelAdmin):
    pass


class UserResource(resources.ModelResource):

    firstname = Field(attribute='first_name', column_name='firstname')
    lastname = Field(attribute='last_name', column_name='lastname')
    meta = Field(column_name='meta', readonly=True)

    def get_instance(self, instance_loader, row):

        field = self.fields['username']
        params = {}

        params[field.attribute] = field.clean(row)

        return self.get_queryset().filter(**params).first()

    def after_import(self, dataset, result, using_transactions, dry_run, **kwargs):

        if not dry_run:

            for i in range(len(dataset)):

                user = User.objects.get(username=dataset['username'][i])

                queryset = user.usermetadata_set

                for o in range(4, len(dataset.headers)):

                    key = dataset.headers[o]
                    val = dataset[i][o]

                    meta = queryset.filter(key=key).first()

                    if meta:
                        meta.value = val
                    else:
                        meta = queryset.create(key=key, value=val)

                    meta.save()

    def export_resource(self, obj):

        col = super().export_resource(obj)

        payload = ''
        for o in obj.usermetadata_set.all():

            payload += '[{id}:{key}:{value}]'.format(**{
                                                            'id': o.id,
                                                            'key': o.key,
                                                            'value': o.value,
            })

        # set usermeta
        col[len(col)-1] = payload

        return col

    class Meta:
        model = User
        fields = (
            'username',
            'email',
            'usermetadata',
        )
        export_order = (
            'username',
            'firstname',
            'lastname',
            'email',
            'meta',
        )


class UserMetaInline(admin.TabularInline):
    model = UserMetaData

class UserAdmin(UAdmin,
                ImportExportModelAdmin,
                ImportExportActionModelAdmin):

    formats = [base_formats.CSV,]

    resource_class = UserResource

    inlines = [UserMetaInline,]


    def import_action(self, request, *args, **kwargs):

        if not self.has_import_permission(request):
            raise PermissionDenied

        if request.method == "GET":
            return super().import_action(request, *args, **kwargs)


        context = self.get_import_context_data()

        import_formats = self.get_import_formats()
        form_type = self.get_import_form()
        form_kwargs = self.get_form_kwargs(form_type, *args, **kwargs)

        form = form_type(import_formats,
                         request.POST or None,
                         request.FILES or None,
                         **form_kwargs)

        # PREVIEW
        if request.POST and form.is_valid():
            input_format = import_formats[
                    int(form.cleaned_data['input_format'])
            ]()

            import_file = form.cleaned_data['import_file']

            tmp_storage = self.write_to_tmp_storage(import_file, input_format)

            try:
                data = tmp_storage.read(input_format.get_read_mode())
                if not input_format.is_binary() and self.from_encoding:
                    data = force_str(data, self.from_encoding)
                dataset = input_format.create_dataset(data)
            except UnicodeDecodeError as e:
                return HttpResponse(_(u"<h1>Imported file has a wrong encoding: %s</h1>" % e))
            except Exception as e:
                return HttpResponse(_(u"<h1>%s encountered while trying to read file: %s</h1>" % (type(e).__name__, import_file.name)))

            res_kwargs = self.get_import_resource_kwargs(request, form=form, *args, **kwargs)
            resource = self.get_import_resource_class()(**res_kwargs)

            imp_kwargs = self.get_import_data_kwargs(request, form=form, *args, **kwargs)
            result = resource.import_data(dataset, dry_run=True,
                                          raise_errors=False,
                                          file_name=import_file.name,
                                          user=request.user,
                                          **imp_kwargs)

            # DRAW PREVIEW HACK
            rows = result.valid_rows()
            for i in range(len(rows)):

                for o in range(4, len(dataset.headers)):

                    val = dataset[i][o]

                    if o < len(rows[i].diff):

                        rows[i].diff[o] = val
                        continue

                    rows[i].diff.append(val)

            result.diff_headers = dataset.headers

            context['result'] = result

            if not result.has_errors() and not result.has_validation_errors():
                initial = {
                        'import_file_name': tmp_storage.name,
                        'original_file_name': import_file.name,
                        'input_format': form.cleaned_data['input_format'],
                }
                confirm_form = self.get_confirm_import_form()
                initial = self.get_form_kwargs(form=form, **initial)
                context['confirm_form'] = confirm_form(initial=initial)

        context.update(self.admin_site.each_context(request))

        context['title'] = _("Import")
        context['form'] = form
        context['opts'] = self.model._meta
        context['fields'] = dataset.headers

        request.current_app = self.admin_site.name

        return TemplateResponse(request, [self.import_template_name],
                    context)

admin.site.unregister(User)
admin.site.register(User, UserAdmin)
