from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist

from ..models.dynamic import Friendship, FriendshipStatus, NetworkerFriendTrigger
from ..models.static import MLNError

def _get_friendship(user, relation_id):
	try:
		friendship = Friendship.objects.get(id=relation_id)
	except ObjectDoesNotExist:
		raise RuntimeError("No friendship relation with ID %i exists" % relation_id)
	if friendship.from_user != user and friendship.to_user != user:
		raise RuntimeError("%s is not related to user %s" % (friendship, user))
	return friendship

def send_friend_invite(user, invitee_name):
	"""
	Send a friend request to someone.
	Raise RuntimeError if no user with the specified username exists.
	Raise RuntimeError if the user already is a friend or blocked friend.
	"""
	try:
		invitee = User.objects.get(username=invitee_name)
	except ObjectDoesNotExist:
		raise RuntimeError("No user with the username %s exists" % invitee_name)
	try:
		friendship = user.outgoing_friendships.get(to_user=invitee)
		if friendship.status == FriendshipStatus.PENDING:
			return
		raise RuntimeError("Friendship to user %s already exists" % invitee_name)
	except ObjectDoesNotExist:
		pass
	try:
		cond = NetworkerFriendshipCondition.objects.get(networker=invitee)
		# networker
		if cond.condition_id is None:
			success = True
		else:
			success = user.inventory.filter(item_id=cond.condition_id).exists()
		if success:
			user.outgoing_friendships.create(to_user=invitee, status=FriendshipStatus.FRIEND)
			user.messages.create(sender=invitee, body_id=cond.success_body_id)
		else:
			user.messages.create(sender=invitee, body_id=cond.failure_body_id)
	except ObjectDoesNotExist:
		# normal user
		user.outgoing_friendships.create(to_user=invitee, status=FriendshipStatus.PENDING)

def handle_friend_invite_response(user, relation_id, accept):
	"""
	Accept or decline a friend request.
	Raise RuntimeError if
	- the friendship does not exist
	- the relation does not relate to this user, or
	- the relation is not a pending relation.
	"""
	relation = _get_friendship(user, relation_id)
	if relation.to_user != user:
		raise RuntimeError("%s is not related to this user" % relation)
	if relation.status != FriendshipStatus.PENDING:
		raise RuntimeError("%s is not a pending relation" % relation)
	if accept:
		relation.status = FriendshipStatus.FRIEND
		relation.save()
	else:
		relation.delete()

def remove_friend(user, relation_id):
	"""
	Remove a friend from the user's friend list.
	Raise RuntimeError if
	- the friendship does not exist
	- the relation does not relate to this user, or
	- the relation is not a friend or blocked relation.
	Raise MLNError if the the user is blocked.
	"""
	relation = _get_friendship(user, relation_id)
	if relation.status not in (FriendshipStatus.FRIEND, FriendshipStatus.BLOCKED):
		raise RuntimeError("%s is not a friend or blocked relation" % relation)
	if relation.status == FriendshipStatus.BLOCKED and relation.from_user != user:
		raise MLNError(MLNError.YOU_ARE_BLOCKED)
	relation.delete()

def block_friend(user, relation_id):
	"""
	Block a friend.
	Raise RuntimeError if
	- the friendship does not exist
	- the relation does not relate to this user, or
	- the relation is not a friend relation.
	"""
	relation = _get_friendship(user, relation_id)
	if relation.status != FriendshipStatus.FRIEND:
		raise RuntimeError("%s is not a friend relation" % relation)
	# the direction of the relation is important for blocked friends
	if relation.to_user == user:
		friend = relation.from_user
		relation.from_user = user
		relation.to_user = friend
	relation.status = FriendshipStatus.BLOCKED
	relation.save()

def unblock_friend(user, relation_id):
	"""
	Unblock a friend.
	Raise RuntimeError if
	- the friendship does not exist
	- the relation does not relate to this user, or
	- the relation is not a blocked relation.
	Raise MLNError if the user is the one who has been blocked instead of the blocker.
	"""
	relation = _get_friendship(user, relation_id)
	if relation.status != FriendshipStatus.BLOCKED:
		raise RuntimeError("%s is not a blocked relation" % relation)
	if relation.from_user != user:
		raise MLNError(MLNError.YOU_ARE_BLOCKED)
	relation.status = FriendshipStatus.FRIEND
	relation.save()

def are_friends(user, other_user_id):
	"""Return whether the users are friends."""
	return user.outgoing_friendships.filter(to_user_id=other_user_id, status=FriendshipStatus.FRIEND).exists() or user.incoming_friendships.filter(from_user_id=other_user_id, status=FriendshipStatus.FRIEND).exists()
