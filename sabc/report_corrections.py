"""One revision allowance shared by report drafting, review and resumed jobs."""
MAX_REVISIONS = 4


class ReportCorrections:
    def __init__(self, state=None, checkpoint=None):
        self.state = state if state is not None else {'count': 0}
        self.checkpoint = checkpoint

    @property
    def count(self):
        return self.state.get('count', 0)

    @property
    def final(self):
        return self.count >= MAX_REVISIONS

    def retry(self, role, failure):
        if self.final:
            raise failure
        self.state.update(count=self.count + 1, role=role, retry_messages=failure.retry_messages)
        if self.checkpoint:
            self.checkpoint()

    def revised(self):
        if not self.final:
            self.state['count'] = self.count + 1

    def messages(self, role):
        return self.state.get('retry_messages', []) if self.state.get('role') == role else []

    def clear_retry(self, role):
        if self.state.get('role') == role:
            self.state.pop('role', None)
            self.state.pop('retry_messages', None)
