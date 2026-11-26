import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from provider_detect import detect_provider  # noqa: E402


class TestHostPatterns(unittest.TestCase):
    def test_s3_bucket_address(self):
        d = detect_provider("https://my-bucket.s3.eu-west-1.amazonaws.com/file.pdf")
        self.assertEqual(d["provider"], "aws-s3")
        self.assertIn("URL itself", d["source"])

    def test_s3_website_address(self):
        d = detect_provider("https://s3.amazonaws.com/my-bucket")
        self.assertEqual(d["provider"], "aws-s3")

    def test_generic_amazonaws_is_aws(self):
        d = detect_provider("https://my-app.elasticbeanstalk.amazonaws.com")
        self.assertEqual(d["provider"], "aws-ec2")

    def test_cloudfront_is_aws(self):
        d = detect_provider("https://d1234abcd.cloudfront.net/index.html")
        self.assertEqual(d["provider"], "aws-ec2")

    def test_azure_websites(self):
        d = detect_provider("https://my-shop.azurewebsites.net")
        self.assertEqual(d["provider"], "azure-vm")

    def test_azure_blob(self):
        d = detect_provider("https://acct.blob.core.windows.net/container/x")
        self.assertEqual(d["provider"], "azure-vm")

    def test_cloud_run_is_google(self):
        d = detect_provider("https://api-abc123.run.app/health")
        self.assertEqual(d["provider"], "gcp-compute")

    def test_firebase_is_google(self):
        d = detect_provider("https://my-project.web.app")
        self.assertEqual(d["provider"], "gcp-compute")

    def test_pages_dev_is_cloudflare(self):
        d = detect_provider("https://my-site.pages.dev")
        self.assertEqual(d["provider"], "cloudflare-workers")

    def test_workers_dev_is_cloudflare(self):
        d = detect_provider("https://api.myname.workers.dev")
        self.assertEqual(d["provider"], "cloudflare-workers")

    def test_spaces_is_digitalocean(self):
        d = detect_provider("https://bucket.fra1.digitaloceanspaces.com/x")
        self.assertEqual(d["provider"], "digitalocean-spaces")

    def test_custom_domain_no_match(self):
        self.assertIsNone(detect_provider("https://www.example.com"))

    def test_bare_domain_without_scheme(self):
        d = detect_provider("my-site.pages.dev")
        self.assertEqual(d["provider"], "cloudflare-workers")


class TestHeaderSignals(unittest.TestCase):
    def test_cf_ray_means_cloudflare(self):
        d = detect_provider("https://www.example.com", {"cf-ray": "8f00-LHR"})
        self.assertEqual(d["provider"], "cloudflare-workers")
        self.assertIn("headers", d["source"])

    def test_cloudflare_server_header(self):
        d = detect_provider("https://www.example.com", {"Server": "cloudflare"})
        self.assertEqual(d["provider"], "cloudflare-workers")

    def test_amazons3_server_header(self):
        d = detect_provider("https://files.example.com", {"Server": "AmazonS3"})
        self.assertEqual(d["provider"], "aws-s3")

    def test_amz_headers_mean_aws(self):
        d = detect_provider("https://api.example.com", {"x-amz-request-id": "ABC123"})
        self.assertEqual(d["provider"], "aws-ec2")

    def test_azure_headers(self):
        d = detect_provider("https://api.example.com", {"x-ms-request-id": "abc"})
        self.assertEqual(d["provider"], "azure-vm")

    def test_google_server_header(self):
        d = detect_provider("https://www.example.com", {"Server": "gws"})
        self.assertEqual(d["provider"], "gcp-compute")

    def test_uninformative_headers_no_match(self):
        d = detect_provider("https://www.example.com", {"Server": "nginx/1.24"})
        self.assertIsNone(d)

    def test_url_pattern_beats_headers(self):
        # A Pages site is Cloudflare by address even if a proxy added
        # unrelated headers; the product-specific address wins.
        d = detect_provider("https://my-site.pages.dev", {"x-ms-request-id": "abc"})
        self.assertEqual(d["provider"], "cloudflare-workers")


if __name__ == "__main__":
    unittest.main()
