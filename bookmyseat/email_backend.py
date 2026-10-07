import ssl
import smtplib
from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend as DjangoEmailBackend
from django.core.mail.utils import DNS_NAME


class CustomSMTPEmailBackend(DjangoEmailBackend):
    """
    SMTP EmailBackend compatible with Python 3.12+ and Django 3.2.
    In Python 3.12, 'keyfile' and 'certfile' parameters were removed from
    smtplib.SMTP.starttls(), requiring an ssl.SSLContext object instead.
    """

    def open(self):
        """
        Ensure an open connection to the email server. Return whether or not a
        new connection was required (True or False) or None if an exception
        passed silently.
        """
        if self.connection:
            return False

        connection_params = {'local_hostname': DNS_NAME.get_fqdn()}
        if self.timeout is not None:
            connection_params['timeout'] = self.timeout

        # Build SSL Context if needed
        ssl_context = ssl.create_default_context()
        if self.ssl_certfile or self.ssl_keyfile:
            ssl_context.load_cert_chain(self.ssl_certfile, self.ssl_keyfile)

        if self.use_ssl:
            connection_params['context'] = ssl_context

        try:
            self.connection = self.connection_class(self.host, self.port, **connection_params)

            # TLS/SSL are mutually exclusive, so only attempt TLS over non-secure connections
            if not self.use_ssl and self.use_tls:
                self.connection.starttls(context=ssl_context)

            if self.username and self.password:
                self.connection.login(self.username, self.password)
            return True
        except OSError:
            if not self.fail_silently:
                raise
