from ..models.dynamic import Attachment, FriendshipStatus, Message
from ..models.static import MessageBody, NetworkerReplyTrigger
from .friend import are_friends
from .inventory import add_inv_item, remove_inv_item

def _check_recipient(user, recipient_id):
	if not user.profile.is_networker:
		if not are_friends(user, recipient_id):
			raise RuntimeError("User with ID %i is not a friend of %s" % (recipient_id, user))

def _get_message(user, message_id):
	message = Message.objects.get(id=message_id)
	if message.recipient != user:
		raise RuntimeError("%s is not addressed to user %s" % (message, user))
	return message

def create_attachment(message, item_id, qty):
	"""Remove items from the user's inventory and attach it to the message."""
	remove_inv_item(message.sender, item_id, qty)
	message.attachments.create(item_id=item_id, qty=qty)

def delete_message(user, message_id):
	"""Delete a message from the user's inbox, detaching any attachments."""
	message = detach_attachments(user, message_id)
	message.delete()

def detach_attachments(user, message_id):
	"""Remove attachments from a message and place them in the user's inventory."""
	message = _get_message(user, message_id)
	for attachment in message.attachments.all():
		add_inv_item(user, attachment.item_id, attachment.qty)
	message.attachments.all().delete()
	return message

def easy_reply(user, recipient_id, org_body_id, body_id):
	"""Send a reply from a list of suggested replies."""
	_check_recipient(user, recipient_id)
	if not user.messages.filter(body_id=org_body_id, sender_id=recipient_id).exists():
		raise RuntimeError("User %s does not have a message with body ID %i from user with ID %i to reply to" % (user, org_body_id, recipient_id))
	body = MessageBody.objects.get(id=org_body_id)
	if not body.easy_replies.filter(id=body_id).exists():
		raise RuntimeError("Message body with ID %i is not an easy reply of %s" % (body_id, body))
	return Message.objects.create(sender=user, recipient_id=recipient_id, body_id=body_id, reply_body_id=org_body_id)

def open_message(user, message_id):
	"""Get a message and mark it as read."""
	message = _get_message(user, message_id)
	message.is_read = True
	message.save()
	return message

def send_message(user, recipient_id, body_id):
	"""Send a message to someone."""
	_check_recipient(user, recipient_id)
	return Message.objects.create(sender=user, recipient_id=recipient_id, body_id=body_id)
