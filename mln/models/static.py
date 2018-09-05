"""
Read-only models used to describe general MLN concepts and data that won't change (except in the case of an update of MLN itself), not dynamic data like users.
These include items and associated info, "about me" questions & answers and message texts.
"""
from enum import auto, Enum

from django.db import models
from django.db.models import Q

# can't change this without also changing the xml - error descriptions are clientside
class MLNError(Exception):
	"""
	An error with an error message that will be shown to the user.
	The displayed messages are actually mail messages in a hidden category.
	As such, this list of raw IDs is not completely ideal and will break when message IDs are reassigned.
	"""
	OPERATION_FAILED = 46304
	YOU_ARE_BLOCKED = 46305
	ALREADY_FRIENDS = 46307
	INVITATION_ALREADY_EXISTS = 46308
	ITEM_MISSING = 46309
	ITEM_IS_NOT_MAILABLE = 46310
	MODULE_ALREADY_SETUP = 46311
	MODULE_IS_NOT_READY = 46312
	OUT_OF_VOTES = 46313
	MLN_OFFLINE = 47570
	MEMBER_NOT_FOUND = 52256

	def __init__(self, id):
		super().__init__()
		self.id = id

class ItemType(Enum):
	"""Types of items. The main use is to place items into different inventory tabs."""
	BACKGROUND = auto()
	BADGE = auto()
	BLUEPRINT = auto()
	ITEM = auto()
	LOOP = auto()
	MASTERPIECE = auto()
	MODULE = auto()
	MOVIE = auto()
	SKIN = auto()
	STICKER = auto()

def EnumField(enum, **kwargs):
	"""Utility function to automatically create a field with choices from a python enum."""
	return models.PositiveSmallIntegerField(choices=[(member.value, member.name.lower()) for member in enum], **kwargs)

class ItemInfo(models.Model):
	"""
	An item.
	This is not the class for the inventory contents of users, for that, see InventoryStack.
	Instead, this describes abstract items that exist in MLN.
	In MLN, almost everything you can possess is an item, including (abstract) modules, loops, stickers, page skins and more. See ItemType for a complete list.
	"""
	name = models.CharField(max_length=64)
	type = EnumField(ItemType)

	class Meta:
		ordering = ("name",)

	def __str__(self):
		return self.name

class Stack(models.Model):
	"""
	Multiple instances of an item.
	This abstract class is used as a base for more specific stacks with a certain purpose, like inventory stacks or attachments.
	"""
	item = models.ForeignKey(ItemInfo, related_name="+", on_delete=models.CASCADE)
	qty = models.PositiveSmallIntegerField()

	class Meta:
		abstract = True

	def __str__(self):
		return "%ix %s (%s)" % (self.qty, self.item.name, self.item.get_type_display())

class BlueprintInfo(models.Model):
	"""Stores which item the blueprint produces."""
	item = models.OneToOneField(ItemInfo, related_name="+", on_delete=models.CASCADE)
	build = models.OneToOneField(ItemInfo, related_name="+", on_delete=models.CASCADE, limit_choices_to=Q(type=ItemType.BADGE.value) | Q(type=ItemType.ITEM.value) | Q(type=ItemType.MASTERPIECE.value) | Q(type=ItemType.MODULE.value) | Q(type=ItemType.MOVIE.value) | Q(type=ItemType.SKIN.value))

	def __str__(self):
		return str(self.item)

class BlueprintRequirement(Stack):
	"""Stores how many of an item a blueprint needs to produce an item."""
	blueprint_item = models.ForeignKey(ItemInfo, related_name="+", on_delete=models.CASCADE)
	item = models.ForeignKey(ItemInfo, related_name="+", on_delete=models.CASCADE, limit_choices_to=Q(type=ItemType.BADGE.value) | Q(type=ItemType.ITEM.value))

	def __str__(self):
		return "%s needs %s" % (self.blueprint_item, super().__str__())

class ModuleInfo(models.Model):
	"""Stores whether the module is executable, setupable, and its editor type. The editor type defines which save data the module uses."""
	item = models.OneToOneField(ItemInfo, related_name="+", on_delete=models.CASCADE)
	is_executable = models.BooleanField()
	is_setupable = models.BooleanField()
	href_editor = models.CharField(max_length=256, null=True, blank=True)

	def __str__(self):
		return str(self.item)

class ArcadePrize(Stack):
	"""
	A prize of an arcade module.
	If the arcade is won, it can be obtained at the probability given in the success_rate attribute, in percent.
	The sum of the success rates of all prizes of an arcade should always be 100.
	"""
	module_item = models.ForeignKey(ItemInfo, related_name="+", on_delete=models.CASCADE)
	success_rate = models.PositiveSmallIntegerField()

class ModuleExecutionCost(Stack):
	"""
	Defines the cost guests will have to pay to click on the module.
	The paid items are typically not transferred to the module owner, they are deleted from the system.
	"""
	module_item = models.ForeignKey(ItemInfo, related_name="+", on_delete=models.CASCADE)

class ModuleSetupCost(Stack):
	"""
	Defines the cost owner will have to pay to set up a module.
	This can be retrieved by the owner as long as the module isn't ready for harvest or hasn't been executed.
	"""
	module_item = models.ForeignKey(ItemInfo, related_name="+", on_delete=models.CASCADE)

class ModuleYieldInfo(models.Model):
	"""Defines the item the module "grows", its harvest cap, its growth rate, and the click growth rate."""
	item = models.OneToOneField(ItemInfo, related_name="+", on_delete=models.CASCADE)
	yield_item = models.ForeignKey(ItemInfo, related_name="+", on_delete=models.CASCADE)
	max_yield = models.PositiveSmallIntegerField()
	yield_per_day = models.PositiveSmallIntegerField()
	clicks_per_yield = models.PositiveSmallIntegerField()

	def __str__(self):
		return str(self.item)

class MessageBody(models.Model):
	"""
	A message text, consisting of subject and body.
	As MLN only allows sending prefabricated messages, using one of these is the only way of communication.
	Messages from Networkers also use this class.
	Some message texts have ready-made responses available, called easy replies.
	A common example is an easy reply of "Thanks", used by various message texts.
	"""
	subject = models.CharField(max_length=64)
	text = models.TextField()
	easy_replies = models.ManyToManyField("self", related_name="+", symmetrical=False)

	class Meta:
		verbose_name_plural = "Message bodies"

	def __str__(self):
		return "%s: %s" % (self.subject, self.text)

class MessageReplyType(Enum):
	"""
	Message reply options, defining the combinations of reply and easy reply that can be used on a message.
	I'm not sure how these are associated with messages.
	Currently I just set a message to "normal & easy reply" if it has easy replies available, and "normal reply only" if it doesn't.
	"""
	NORMAL_REPLY_ONLY = 0
	NORMAL_AND_EASY_REPLY = 1
	EASY_REPLY_ONLY = 2
	NO_REPLY = 3

class Question(models.Model):
	"""A question for the "About me" section."""
	text = models.CharField(max_length=64)
	mandatory = models.BooleanField()

	def __str__(self):
		return self.text

class Answer(models.Model):
	"""An answer to an "About me" question."""
	question = models.ForeignKey(Question, related_name="+", on_delete=models.CASCADE)
	text = models.CharField(max_length=64)

	def __str__(self):
		return self.text

class Color(models.Model):
	"""A color, used for page and module backgrounds."""
	color = models.IntegerField()

	def __str__(self):
		return hex(self.color)

class ModuleSkin(models.Model):
	"""A skin (background pattern) of a module."""
	name = models.CharField(max_length=64)

	def __str__(self):
		return self.name

class StartingStack(Stack):
	"""A stack that users start off with in their inventory when they create an account."""
