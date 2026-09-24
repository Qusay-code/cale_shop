"""Upload handlers that reject oversized files while they are received."""

from django.core.exceptions import RequestDataTooBig
from django.core.files.uploadhandler import FileUploadHandler

from .services.images import MAX_UPLOAD_SIZE


class ImageSizeLimitUploadHandler(FileUploadHandler):
    """Reject any uploaded file larger than the image pipeline accepts."""

    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.file_size = 0

    def receive_data_chunk(self, raw_data, start):
        self.file_size += len(raw_data)
        if self.file_size > MAX_UPLOAD_SIZE:
            raise RequestDataTooBig(
                f"Uploaded file exceeds the {MAX_UPLOAD_SIZE}-byte limit."
            )
        return raw_data

    def file_complete(self, file_size):
        return None
