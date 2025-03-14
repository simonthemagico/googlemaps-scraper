# -*- coding: utf-8 -*-

from time import sleep

from .base import Capability, BaseObject, StringField, UserError, BytesField
from ..exceptions import RecaptchaQuestion, NocaptchaQuestion, FuncaptchaQuestion, ImageCaptchaQuestion


__all__ = [
    'CapCaptchaSolver',
    'SolverJob', 'RecaptchaJob', 'NocaptchaJob', 'ImageCaptchaJob',
    'CaptchaError', 'UnsolvableCaptcha', 'InvalidCaptcha', 'InsufficientFunds',
    'exception_to_job',
]


class SolverJob(BaseObject):
    solution = StringField('CAPTCHA solution')


class RecaptchaJob(SolverJob):
    site_url = StringField('Site URL for ReCaptcha service')
    site_key = StringField('Site key for ReCaptcha service')

    solution_challenge = StringField('Challenge ID of the solution (output value)')


class NocaptchaJob(SolverJob):
    site_url = StringField('Site URL for NoCaptcha service')
    site_key = StringField('Site key for NoCaptcha service')


class FuncaptchaJob(SolverJob):
    site_url = StringField('Site URL for FunCaptcha service')
    site_key = StringField('Site key for FunCaptcha service')
    sub_domain = StringField('Required for some complex cases, but Funcaptcha integrations run without it')


class ImageCaptchaJob(SolverJob):
    image = BytesField('data of the image to solve')


class CaptchaError(UserError):
    """Generic solving error"""


class InvalidCaptcha(CaptchaError):
    """CAPTCHA cannot be used (e.g. invalid image format)"""


class UnsolvableCaptcha(CaptchaError):
    """CAPTCHA is too hard or impossible"""


class InsufficientFunds(CaptchaError):
    """Not enough funds to pay solution"""


def exception_to_job(exc):
    if isinstance(exc, RecaptchaQuestion):
        job = RecaptchaJob()
        job.site_url = exc.website_url
        job.site_key = exc.website_key
    elif isinstance(exc, NocaptchaQuestion):
        job = NocaptchaJob()
        job.site_url = exc.website_url
        job.site_key = exc.website_key
    elif isinstance(exc, FuncaptchaQuestion):
        job = FuncaptchaJob()
        job.site_url = exc.website_url
        job.site_key = exc.website_key
        job.sub_domain = exc.sub_domain
    elif isinstance(exc, ImageCaptchaQuestion):
        job = ImageCaptchaJob()
        job.image = exc.image_data
    else:
        raise NotImplementedError()

    return job


class CapCaptchaSolver(Capability):
    """
    Provide CAPTCHA solving
    """

    RETRIES = 30
    WAIT_TIME = 2

    def create_job(self, job):
        """Start a CAPTCHA solving job

        The `job.id` shall be filled. The CAPTCHA is not solved yet when the method returns.

        :param job: job to start
        :type job: :class:`SolverJob`
        :raises: :class:`NotImplementedError` if CAPTCHA type is not supported
        :raises: :class:`CaptchaError` in case of other error
        """
        raise NotImplementedError()

    def poll_job(self, job):
        """Check if a job was solved

        If `job` is solved, return True and fill `job.solution`.
        Return False if solution is still pending.
        In case of solving problem, an exception may be raised.

        It should not wait for the solution but return the current state.

        :param job: job to check and to fill when solved
        :type job: :class:`SolverJob`
        :returns: True if the job was solved
        :rtype: bool
        :raises: :class:`CaptchaError`
        """
        raise NotImplementedError()

    def solve_catpcha_blocking(self, job):
        """Start a CAPTCHA solving job and wait for its solution

        :param job: job to start and solve
        :type job: :class:`SolverJob`
        :raises: :class:`CaptchaError`
        """

        self.create_job(job)
        for i in range(self.RETRIES):
            sleep(self.WAIT_TIME)
            if self.poll_job(job):
                return job

    def report_wrong_solution(self, job):
        """Report a solved job as a wrong solution

        Sometimes, jobs are solved, but the solution is rejected by the CAPTCHA
        site because the solution is wrong.
        This method reports the solution as wrong to the CAPTCHA solver.

        :param job: job to flag
        :type job: :class:`SolverJob`
        """
        raise NotImplementedError()

    def get_balance(self):
        """Get the prepaid balance left

        :rtype: float
        """
        raise NotImplementedError()
