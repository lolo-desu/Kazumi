"""Store credentials in the desktop Secret Service, outside profile backups."""

import hashlib


class Vault:
    def __init__(self, app, profile):
        import gi

        gi.require_version("Secret", "1")
        from gi.repository import Secret

        self.secret = Secret
        self.schema = Secret.Schema.new(
            "io.github.lolo_desu.NativeCredentials",
            Secret.SchemaFlags.NONE,
            {
                "application": Secret.SchemaAttributeType.STRING,
                "profile": Secret.SchemaAttributeType.STRING,
                "service": Secret.SchemaAttributeType.STRING,
            },
        )
        self.attributes = {
            "application": app,
            "profile": hashlib.sha256(str(profile.resolve()).encode()).hexdigest(),
        }

    def get(self, service):
        return self.secret.password_lookup_sync(
            self.schema, {**self.attributes, "service": service}, None
        )

    def set(self, service, password):
        ok = self.secret.password_store_sync(
            self.schema,
            {**self.attributes, "service": service},
            self.secret.COLLECTION_DEFAULT,
            self.attributes["application"] + " · " + service,
            password,
            None,
        )
        if not ok:
            raise RuntimeError("无法保存到系统密钥环，凭据未保存")

    def remove(self, service):
        self.secret.password_clear_sync(
            self.schema, {**self.attributes, "service": service}, None
        )
