import os
import time

from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404, HttpResponseNotModified
from django.test import TestCase
from django.utils.http import http_date

from filer import settings as filer_settings
from filer.models import File
from filer.server.backends.default import DefaultServer
from filer.server.backends.nginx import NginxXAccelRedirectServer
from filer.server.backends.xsendfile import ApacheXSendfileServer
from tests.helpers import create_image


class Mock():
    pass


class BaseServerBackendTestCase(TestCase):
    def setUp(self):
        original_filename, mime_type = 'testimage.jpg', 'image/jpeg'
        file_obj = SimpleUploadedFile(
            name=original_filename,
            content=create_image().tobytes(),
            content_type=mime_type)
        self.filer_file = File.objects.create(
            is_public=False,
            file=file_obj,
            original_filename=original_filename,
            mime_type=mime_type)

    def tearDown(self):
        self.filer_file.delete()


class DefaultServerTestCase(BaseServerBackendTestCase):
    def test_normal(self):
        server = DefaultServer()
        request = Mock()
        request.headers = {}
        response = server.serve(request, self.filer_file)
        self.assertTrue(response.has_header('Last-Modified'))

    def test_save_as(self):
        server = DefaultServer()
        request = Mock()
        request.headers = {}
        response = server.serve(request, self.filer_file, save_as=True)
        self.assertEqual(response['Content-Disposition'], 'attachment; filename=testimage.jpg')

        response = server.serve(request, self.filer_file, save_as=False)
        self.assertFalse(response.has_header('Content-Disposition'))

        response = server.serve(request, self.filer_file, save_as='whatever.png')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename=whatever.png')

    def test_not_modified(self):
        server = DefaultServer()
        request = Mock()
        request.headers = {'HTTP_IF_MODIFIED_SINCE': http_date(time.time())}
        response = server.serve(request, self.filer_file)
        self.assertTrue(isinstance(response, HttpResponseNotModified))

    def test_missing_file(self):
        server = DefaultServer()
        request = Mock()
        request.headers = {}
        os.remove(self.filer_file.file.path)
        self.assertRaises(Http404, server.serve, *(request, self.filer_file.file))


class NginxServerTestCase(BaseServerBackendTestCase):
    def setUp(self):
        super().setUp()
        self.server = NginxXAccelRedirectServer(
            location=filer_settings.FILER_PRIVATEMEDIA_STORAGE.location,
            nginx_location='mylocation',
        )

    def test_normal(self):
        request = Mock()
        request.headers = {}
        response = self.server.serve(request, self.filer_file)
        headers = dict(response.items())
        self.assertTrue(response.has_header('X-Accel-Redirect'))
        self.assertTrue(headers['X-Accel-Redirect'].startswith(self.server.nginx_location))
        # make sure the file object was never opened (otherwise the whole delegating to nginx would kinda
        # be useless)
        self.assertTrue(self.filer_file.file.closed)

    def test_missing_file(self):
        """
        this backend should not even notice if the file is missing.
        """
        request = Mock()
        request.headers = {}
        os.remove(self.filer_file.file.path)
        response = self.server.serve(request, self.filer_file)
        headers = dict(response.items())
        self.assertTrue(response.has_header('X-Accel-Redirect'))
        self.assertTrue(headers['X-Accel-Redirect'].startswith(self.server.nginx_location))
        self.assertTrue(self.filer_file.file.closed)


class XSendfileServerTestCase(BaseServerBackendTestCase):
    def setUp(self):
        super().setUp()
        self.server = ApacheXSendfileServer()

    def test_normal(self):
        request = Mock()
        request.headers = {}
        response = self.server.serve(request, self.filer_file)
        headers = dict(response.items())
        self.assertTrue(response.has_header('X-Sendfile'))
        self.assertEqual(headers['X-Sendfile'], self.filer_file.file.path)
        # make sure the file object was never opened (otherwise the whole delegating to nginx would kinda
        # be useless)
        self.assertTrue(self.filer_file.file.closed)

    def test_missing_file(self):
        """
        this backend should not even notice if the file is missing.
        """
        request = Mock()
        request.headers = {}
        os.remove(self.filer_file.file.path)
        response = self.server.serve(request, self.filer_file)
        headers = dict(response.items())
        self.assertTrue(response.has_header('X-Sendfile'))
        self.assertEqual(headers['X-Sendfile'], self.filer_file.file.path)
        # make sure the file object was never opened (otherwise the whole delegating to nginx would kinda
        # be useless)
        self.assertTrue(self.filer_file.file.closed)
