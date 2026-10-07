from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from movies.models import Movie

class UserAppTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='user1',
            password='TestPassword123!',
            email='user1@example.com'
        )

    def test_home_page(self):
        Movie.objects.create(
            name='Test Movie',
            image='movies/test.jpg',
            rating=8.5,
            cast='Test Cast',
            description='Test Desc'
        )
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Movie')

    def test_register_view_get(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Register')

    def test_register_view_post_success(self):
        response = self.client.post(reverse('register'), {
            'username': 'user2',
            'email': 'user2@example.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!'
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='user2').exists())

    def test_login_view(self):
        response = self.client.post(reverse('login'), {
            'username': 'user1',
            'password': 'TestPassword123!'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/')

    def test_profile_requires_login(self):
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_profile_view_authenticated(self):
        self.client.login(username='user1', password='TestPassword123!')
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'user1')

    def test_logout_view_get_and_post(self):
        self.client.login(username='user1', password='TestPassword123!')
        # Test POST logout
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'You have been logged out')

        # Test GET logout
        self.client.login(username='user1', password='TestPassword123!')
        response = self.client.get(reverse('logout'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'You have been logged out')

    def test_staff_login_redirects_to_movie_admin_dashboard(self):
        User.objects.create_user(username='staffuser', password='StaffPassword123!', is_staff=True)
        response = self.client.post(reverse('login'), {
            'username': 'staffuser',
            'password': 'StaffPassword123!'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('movie_admin_dashboard'))

    def test_superuser_login_redirects_to_movie_admin_dashboard(self):
        User.objects.create_superuser(username='superadmin', password='SuperPassword123!', email='admin@test.com')
        response = self.client.post(reverse('login'), {
            'username': 'superadmin',
            'password': 'SuperPassword123!'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('movie_admin_dashboard'))

    def test_login_with_next_param_redirects_to_next(self):
        response = self.client.post(reverse('login') + '?next=/profile/', {
            'username': 'user1',
            'password': 'TestPassword123!'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/profile/')

