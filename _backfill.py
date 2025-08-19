from dotenv import load_dotenv

from app import create_app, db
from app.models import Post, PostLink
from app.models import rebuild_post_edges  # reuse the same function

load_dotenv()


def run():
    app = create_app()
    with app.app_context():
        posts = Post.query.order_by(Post.timestamp.asc()).all()
        for i, post in enumerate(posts, 1):
            # Rebuild edges for each post
            db.session.query(PostLink).filter_by(src_post_id=post.id).delete()
            rebuild_post_edges(db.session, post)

            if i % 200 == 0:
                db.session.commit()
        db.session.commit()
        print(f"Backfilled links for {len(posts)} posts.")


if __name__ == "__main__":
    run()
