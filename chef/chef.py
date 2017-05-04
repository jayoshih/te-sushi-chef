import youtube_dl
from chef.data.data import SOURCE_DOMAIN, SOURCE_ID, CHANNEL_TITLE, CHANNEL_THUMBNAIL, DATA_SOURCE
from le_utils.constants import content_kinds, file_formats, licenses, languages
from ricecooker.classes import nodes, files

def construct_channel(**kwargs):

    channel = nodes.ChannelNode(
        source_domain=SOURCE_DOMAIN,
        source_id=SOURCE_ID,
        title=CHANNEL_TITLE,
        thumbnail=CHANNEL_THUMBNAIL,
    )

    _build_tree(channel, DATA_SOURCE)

    return channel


def _build_tree(parent, data_source):
    """
    Parse nodes given in `sourcetree` and add as children of `node`.
    """
    for child_source_node in data_source:

        if child_source_node.get('children'):
            child_node = nodes.TopicNode(
                source_id=child_source_node["id"],
                title=child_source_node["title"],
            )
            parent.add_child(child_node)
            _build_tree(child_node, child_source_node.get("children", []))

        else:
            child_node = nodes.VideoNode(
                source_id=child_source_node["id"],
                title=child_source_node["title"],
                license=child_source_node["license"],
                description=create_description(child_source_node),
                derive_thumbnail=True,
                files=[files.YouTubeVideoFile(youtube_id=child_source_node['youtube_id'])],
            )
            for language in child_source_node['subtitle_langs']:
                child_node.add_file(files.YouTubeSubtitleFile(youtube_id=child_source_node['youtube_id'], language=language))
            parent.add_child(child_node)

    return parent

def create_description(source_node):
    description = source_node.get("about") or ""
    if source_node.get("transcript"):
        description += "\n\nTRANSCRIPT: " + source_node.get('transcript')
    if source_node.get('info'):
        description += "\n\nMORE INFO: " + source_node.get('info')
    return description
