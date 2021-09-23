"""
Models for objects that will be created, modified and deleted during runtime.
These include user profiles, inventory stacks and messages.
Since modules have a lot of models associated with them, their models are in dedicated files.
"""
import datetime
from enum import auto, Enum

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import MaxValueValidator
from django.db import models
from django.utils.timezone import now

from ..services.inventory import assert_has_item
from .static import Answer, Color, EnumField, ItemInfo, ItemType, MessageBody, Stack, Question

DAY = datetime.timedelta(days=1)

class Message(models.Model):
	"""
	A message sent from one user to another.
	User messages can only be sent to friends, while messages sent by networkers don't have this restriction.
	Message contents are determined by a prefabricated message text that can be chosen.
	In the case of replies, the original message is also stored, so that the subject can be displayed as RE: <original>.
	Messages can have attachments.
	"""
	sender = models.ForeignKey(User, related_name="+", on_delete=models.CASCADE)
	recipient = models.ForeignKey(User, related_name="messages", on_delete=models.CASCADE)
	body = models.ForeignKey(MessageBody, related_name="+", on_delete=models.CASCADE)
	reply_body = models.ForeignKey(MessageBody, null=True, blank=True, related_name="+", on_delete=models.CASCADE)
	is_read = models.BooleanField(default=False)

	def __str__(self):
		if self.reply_body_id is not None:
			subject = "RE: "+self.reply_body.subject
		else:
			subject = self.body.subject
		return "Message from %s to %s, subject \"%s\", is read: %s" % (self.sender, self.recipient, subject, self.is_read)

class Attachment(Stack):
	"""An attachment, a stack sent with a message."""
	message = models.ForeignKey(Message, related_name="attachments", on_delete=models.CASCADE)

	class Meta:
		constraints = (models.UniqueConstraint(fields=("message", "item"), name="attachment_unique_message_item"),)

	def __str__(self):
		return "%s attached to %s" % (super().__str__(), self.message)

class Profile(models.Model):
	"""
	MLN-specific user data.
	This includes the avatar, user rank, available votes, page skin and page colors.
	"""
	user = models.OneToOneField(User, on_delete=models.CASCADE)
	is_networker = models.BooleanField(default=False)
	avatar = models.CharField(max_length=64, default="0#1,6,1,16,5,1,6,13,2,9,2,2,1,1")
	rank = models.PositiveSmallIntegerField(default=0)
	available_votes = models.PositiveSmallIntegerField(default=20)
	last_vote_update_time = models.DateTimeField(default=now)
	page_skin = models.ForeignKey(ItemInfo, null=True, blank=True, related_name="+", on_delete=models.PROTECT, limit_choices_to={"type": ItemType.SKIN})
	page_color = models.ForeignKey(Color, null=True, blank=True, related_name="+", on_delete=models.CASCADE)
	page_column_color_id = models.PositiveSmallIntegerField(null=True, blank=True, validators=(MaxValueValidator(4),)) # hardcoded for some reason

	def __str__(self):
		return self.user.username

	def clean(self):
		if self.avatar != "png":
			parts = self.avatar.split("#")
			if len(parts) not in (2, 3):
				raise ValidationError({"avatar": "Avatar does not have the right number of parts"})
			if (self.is_networker and parts[0] not in ("0", "1")) or (not self.is_networker and parts[0] != "0"):
				raise ValidationError({"avatar": "First part of avatar should not be %s" % parts[0]})
			avatar_data = parts[1].split(",")
			if not((parts[0] == "0" and len(avatar_data) == 14) or (parts[0] == "1" and len(avatar_data) == 5)):
				raise ValidationError({"avatar": "Data part of avatar has %i values but shouldn't %s" % (len(avatar_data), self.avatar)})
			self.avatar = parts[0]+"#"+parts[1]

		max_votes = 20 + 8 * self.rank
		if self.available_votes >	max_votes:
			raise ValidationError({"available_votes": "Can't have more votes available than the maximum of %i at rank %i" % (max_votes, self.rank)})

		if self.page_skin_id is not None:
			assert_has_item(self.user, self.page_skin_id)

	def update_available_votes(self):
		"""
		Calculate how many votes are available.
		Votes regenerate at a rate determined by rank, but will only be updated if you explicitly call this function.
		"""
		time_since_last_update = now() - self.last_vote_update_time
		max_votes = 20 + 8 * self.rank
		new_votes, time_remainder = divmod(time_since_last_update, (DAY / max_votes))
		if new_votes > 0:
			self.available_votes = min(self.available_votes + new_votes, max_votes)
			self.last_vote_update_time = now() - time_remainder
			self.save()

class AboutMe(models.Model):
	"""Questions and answers the user can choose to display on their page as a bio/profile of themselves."""
	user = models.OneToOneField(User, related_name="about_me", on_delete=models.CASCADE)

	def __str__(self):
		return "%s's about me" % self.user

	def clean(self):
		provided = set()
		for i in range(6):
			question_id = getattr(self, "question_%i_id" % i)
			answer_id = getattr(self, "answer_%i_id" % i)
			provided.add(question_id)
			if not Answer.objects.filter(id=answer_id, question_id=question_id).exists():
				answer = getattr(self, "answer_%i" % i)
				question = getattr(self, "question_%i" % i)
				raise ValidationError({"answer_%i" % i: "Answer %s is not an answer to Question %s" % (answer, question)})
		if len(provided) != 6:
			raise ValidationError("Duplicate questions provided")
		for question in Question.objects.filter(mandatory=True):
			if question.id not in provided:
				raise ValidationError("Mandatory question %s not provided" % question)

for i in range(6):
	AboutMe.add_to_class("question_%i" % i, models.ForeignKey(Question, related_name="+", on_delete=models.PROTECT))
	AboutMe.add_to_class("answer_%i" % i, models.ForeignKey(Answer, related_name="+", on_delete=models.PROTECT))

class InventoryStack(Stack):
	"""A stack of items in the user's inventory."""
	owner = models.ForeignKey(User, related_name="inventory", on_delete=models.CASCADE)

	class Meta:
		constraints = (models.UniqueConstraint(fields=("owner", "item"), name="inventory_stack_unique_owner_item"),)

	def __str__(self):
		return "%s's stack of %s" % (self.owner, super().__str__())

class FriendshipStatus(Enum):
	"""
	Statuses of a friendship relation.
	When a user requests another user to be their friend, the request is pending.
	Once the other user accepts, the status is changed to friend.
	If a user blocks a friend, the status is changed to blocked.
	"""
	FRIEND = auto()
	PENDING = auto()
	BLOCKED = auto()

class Friendship(models.Model):
	"""
	A friendship relation of two users.
	This is also used for friend requests and blocked friends.
	"""
	from_user = models.ForeignKey(User, related_name="outgoing_friendships", on_delete=models.CASCADE) # invite sender
	to_user = models.ForeignKey(User, related_name="incoming_friendships", on_delete=models.CASCADE) # invite recipient
	status = EnumField(FriendshipStatus)

	def __str__(self):
		return "%s -> %s: %s" % (self.from_user, self.to_user, self.get_status_display())

class MessageTemplate(models.Model): 
	"""An action that triggers a networker to send a response to the user."""
	networker = models.ForeignKey(User, null=True, related_name="+", on_delete=models.CASCADE, limit_choices_to={"profile__is_networker": True})
	body = models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='+', to='mln.messagebody')

	# Currently meant for devs to collect data on triggers, later to be properly integrated into the system.
	networker_name = models.CharField(max_length=64, blank=True, null=True)
	trigger = models.TextField(blank=True, null=True)
	source = models.TextField(blank=True, null=True)
	notes = models.TextField(blank=True, null=True)

	def send(self, recipient, sender=None): 
		message = Message.objects.create(sender=sender or self.networker, recipient=recipient, body=self.body)
		for attachment in self.attachments.all():
			message.attachments.create(item_id=attachment.item_id, qty=attachment.qty)

class MessageTemplateAttachment(Stack):
	"""A stack to be attached to a networker message."""
	template = models.ForeignKey(MessageTemplate, related_name="attachments", on_delete=models.CASCADE)

	class Meta:
		constraints = (models.UniqueConstraint(fields=("template", "item"), name="networker_template_attachment_unique_template_item"),)

class NetworkerReplyTrigger(MessageTemplate):
	"""A template for a message that triggers a networker's response."""
	message_body = models.ForeignKey(MessageBody, related_name="+", on_delete=models.CASCADE, blank=True, null=True)
	message_attachment = models.ForeignKey(ItemInfo, related_name="+", on_delete=models.CASCADE, blank=True, null=True)

	def __str__(self):
		return "From %s: %s" % (self.networker, self.response)

	def evaluate(self, message, attachment): 
		return (
			(self.message_body is None or message.body == self.message_body) and  # compare bodies
			(self.message_attachment is None) == (attachment is None) and  # don't compare null attachments
			(self.message_attachment is None or attachment.item == self.message_attachment)  # compare attachments
		)

def get_or_none(cls, *args, **kwargs):
	"""Get a model instance according to the filters, or return None if no matching model instance was found."""
	try:
		return cls.objects.get(*args, **kwargs)
	except ObjectDoesNotExist:
		return None
