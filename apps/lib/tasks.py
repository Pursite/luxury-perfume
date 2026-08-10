"""Celery task base classes shared by application tasks."""

from celery import Task

from apps.lib.log_context import bind_correlation_id, reset_correlation_id


class CorrelatedTask(Task):
    """Expose the broker-generated task ID to structured logs during execution."""

    abstract = True

    def __call__(self, *args, **kwargs):
        task_id = self.request.id
        if not task_id:
            return super().__call__(*args, **kwargs)

        token = bind_correlation_id(task_id)
        try:
            return super().__call__(*args, **kwargs)
        finally:
            reset_correlation_id(token)
