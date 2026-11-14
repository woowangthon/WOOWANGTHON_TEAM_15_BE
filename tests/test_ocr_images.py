import io
import unittest
from unittest.mock import patch

from PIL import Image

from app.services.ocr import ImageInputError, prepare_image


def picture(fmt="PNG", size=(100, 60), **kwargs):
    with Image.new("RGB", size, "white") as image:
        stream = io.BytesIO()
        image.save(stream, format=fmt, **kwargs)
    return stream.getvalue()


class ImageValidationTests(unittest.TestCase):
    def test_jpeg_png_and_exif_rotation(self):
        exif = Image.Exif()
        exif[274] = 6
        image = prepare_image(picture("JPEG", (40, 20), exif=exif), "image/jpeg")
        self.assertEqual(image.size, (20, 40))
        self.assertEqual(image.mode, "RGB")
        image.close()
        image = prepare_image(picture(), "image/png")
        self.assertEqual(image.size, (100, 60))
        image.close()

    def test_corrupt_mislabeled_and_unsupported_images(self):
        for data, mime, expected in [(b"", "image/png", 400), (b"bad", "image/png", 400),
                                     (picture(), "image/jpeg", 415), (b"<svg/>", "image/svg+xml", 415)]:
            with self.subTest(mime=mime), self.assertRaises(ImageInputError) as error:
                prepare_image(data, mime)
            self.assertEqual(error.exception.status_code, expected)

    def test_pixel_and_byte_limits_and_resize(self):
        with patch("app.services.ocr.MAX_IMAGE_PIXELS", 100), self.assertRaises(ImageInputError) as error:
            prepare_image(picture(size=(20, 20)), "image/png")
        self.assertEqual(error.exception.status_code, 413)
        with patch("app.services.ocr.MAX_IMAGE_BYTES", 2), self.assertRaises(ImageInputError) as error:
            prepare_image(b"123", "image/png")
        self.assertEqual(error.exception.status_code, 413)
        image = prepare_image(picture(size=(2000, 500)), "image/png")
        self.assertEqual(image.size, (1600, 400))
        image.close()

    def test_animated_png_is_rejected(self):
        first = Image.new("RGB", (10, 10), "white")
        second = Image.new("RGB", (10, 10), "black")
        stream = io.BytesIO()
        first.save(stream, "PNG", save_all=True, append_images=[second], duration=100)
        first.close()
        second.close()
        with self.assertRaises(ImageInputError) as error:
            prepare_image(stream.getvalue(), "image/png")
        self.assertEqual(error.exception.status_code, 415)

if __name__ == "__main__":
    unittest.main()
