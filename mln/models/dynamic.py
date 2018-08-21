"""
Models for objects that will be created, modified and deleted during runtime.
These include user profiles, inventory stacks and messages.
Since modules have a lot of models associated with them, their models are in dedicated files.
"""
import datetime
from enum import auto, Enum

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils.timezone import now

from .static import Answer, BlueprintInfo, BlueprintRequirement, Color, EnumField, ItemInfo, ItemType, MessageBody, Stack, Question

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
	reply_body = models.ForeignKey(MessageBody, null=True, related_name="+", on_delete=models.CASCADE)
	is_read = models.BooleanField(default=False)

	def __str__(self):
		if self.reply_body_id is not None:
			subject = "RE: "+self.reply_body.subject
		else:
			subject = self.body.subject
		return "Message from %s to %s, subject \"%s\", is read: %s" % (self.sender, self.recipient, subject, self.is_read)

class Attachment(Stack):
	"""An Attachment, a stack sent with a message."""
	message = models.ForeignKey(Message, related_name="attachments", on_delete=models.CASCADE)

	def __str__(self):
		return "%s attached to %s" % (super().__str__(), self.message)

class Profile(models.Model):
	"""
	MLN-specific user data.
	This includes the avatar, user rank, available votes, page skin and page colors, as well as "About me" statements.
	"""
	user = models.OneToOneField(User, on_delete=models.CASCADE)
	avatar = models.CharField(max_length=64, default="0#1,6,1,16,5,1,6,13,2,9,2,2,1,1")
	rank = models.PositiveSmallIntegerField(default=0)
	available_votes = models.PositiveSmallIntegerField(default=20)
	last_vote_update_time = models.DateTimeField(default=now)
	page_skin = models.ForeignKey(ItemInfo, null=True, blank=True, related_name="+", on_delete=models.PROTECT, limit_choices_to={"type": ItemType.SKIN.value})
	page_color = models.ForeignKey(Color, null=True, blank=True, related_name="+", on_delete=models.CASCADE)
	page_column_color_id = models.PositiveSmallIntegerField(null=True) # hardcoded for some reason
	statement_0_q = models.ForeignKey(Question, related_name="+", on_delete=models.PROTECT, default=43520)
	statement_0_a = models.ForeignKey(Answer, related_name="+", on_delete=models.PROTECT, default=46069)
	statement_1_q = models.ForeignKey(Question, related_name="+", on_delete=models.PROTECT, default=43521)
	statement_1_a = models.ForeignKey(Answer, related_name="+", on_delete=models.PROTECT, default=43239)
	statement_2_q = models.ForeignKey(Question, related_name="+", on_delete=models.PROTECT, default=43522)
	statement_2_a = models.ForeignKey(Answer, related_name="+", on_delete=models.PROTECT, default=43525)
	statement_3_q = models.ForeignKey(Question, related_name="+", on_delete=models.PROTECT, default=43523)
	statement_3_a = models.ForeignKey(Answer, related_name="+", on_delete=models.PROTECT, default=46126)
	statement_4_q = models.ForeignKey(Question, related_name="+", on_delete=models.PROTECT, default=46062)
	statement_4_a = models.ForeignKey(Answer, related_name="+", on_delete=models.PROTECT, default=46169)
	statement_5_q = models.ForeignKey(Question, related_name="+", on_delete=models.PROTECT, default=46063)
	statement_5_a = models.ForeignKey(Answer, related_name="+", on_delete=models.PROTECT, default=46170)
	friends = models.ManyToManyField("self", through="Friendship", symmetrical=False)

	def __str__(self):
		return self.user.username

	def add_inv_item(self, item_id, qty=1):
		"""
		Add one or more items to the user's inventory.
		Always use this function instead of creating InventoryStacks directly.
		This function creates a stack only if it does not already exist, and otherwise adds to the existing stack.
		"""
		try:
			stack = self.user.inventory.get(item_id=item_id)
			stack.qty += qty
			stack.save()
			return stack
		except ObjectDoesNotExist:
			return InventoryStack.objects.create(item_id=item_id, qty=qty, owner=self.user)

	def remove_inv_item(self, item_id, qty=1):
		"""
		Remove one or more items from the user's inventory.
		Always use this function instead of modifying InventoryStacks directly.
		This function subtracts the number of items from the stack, and deletes the stack if no more items are left.
		"""
		stack = self.user.inventory.get(item_id=item_id)
		if stack.qty > qty:
			stack.qty -= qty
			stack.save()
		elif stack.qty == qty:
			stack.delete()
		else:
			raise ValueError("Stack of item %i of user %s has fewer items than the %i requested to delete!" % (stack.item_id, self, qty))

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

	def use_blueprint(self, blueprint_id):
		"""
		Use a blueprint to create a new item and add it to the user's inventory.
		Remove the blueprint's requirements from the user's inventory.
		"""
		if not self.user.inventory.filter(item_id=blueprint_id).exists():
			raise RuntimeError("Blueprint not in inventory")
		blueprint_info = BlueprintInfo.objects.get(item_id=blueprint_id)
		requirements = BlueprintRequirement.objects.filter(blueprint_item_id=blueprint_id)
		# verify that requirements are met
		for requirement in requirements:
			if not self.user.inventory.filter(item_id=requirement.item_id, qty__gte=requirement.qty).exists():
				raise RuntimeError("Blueprint requirements not met!")
		# remove required items
		for requirement in requirements:
			self.remove_inv_item(requirement.item_id, requirement.qty)
		# add newly built item
		self.add_inv_item(blueprint_info.build_id)

class InventoryStack(Stack):
	"""A stack of items in the user's inventory."""
	owner = models.ForeignKey(User, related_name="inventory", on_delete=models.CASCADE)

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
	from_profile = models.ForeignKey(Profile, related_name="outgoing_friendships", on_delete=models.CASCADE) # invite sender
	to_profile = models.ForeignKey(Profile, related_name="incoming_friendships", on_delete=models.CASCADE) # invite recipient
	status = EnumField(FriendshipStatus, default=FriendshipStatus.PENDING.value)

	def __str__(self):
		return "%s -> %s: %s" % (self.from_profile.user, self.to_profile.user, self.get_status_display())

def get_or_none(cls, *args, **kwargs):
	"""Get a model instance according to the filters, or return None if no matching model instance was found."""
	try:
		return cls.objects.get(*args, **kwargs)
	except ObjectDoesNotExist:
		return None
