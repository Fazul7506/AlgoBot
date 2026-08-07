class NotificationError(Exception): pass
class DeliveryError(NotificationError): pass
class TemplateRenderError(NotificationError): pass
