"""

    Python module for interfacing with the vRealize API
    Primarily used for reporting initially.

    This thing is kind of a mess so tread carefully while I piece it back together.

"""
# TODO implement logging


__author__ = 'Russell Pope'


import json
import requests
import exceptions

try:
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
except ImportError:
    pass

class Session(object):
    """
    Used to store vRA login session to a specific tenant. The class should be invoked via cls.login()

    This class also includes a series of methods that are helpful in managing the vRA environment.

    The included methods are:

    Session._request(url, request_method="POST", payload)
        Typically used by the class itself to post requests to the vRA REST API

    Session._request(url)
        Used by the class to retrieve data from the vRA REST API

    Session.get_business_groups()
        Returns a dictionary of all business groups available to the logged in user.

    Session.get_entitledcatalogitems()
        Returns a dictionary of all of the catalog items available to the logged in user.

    Session.get_catalogitem_byname(name)
        Returns a dictionary of catalog items containing the string in 'name'


    """

    def __init__(self, username, cloudurl, tenant, auth_header, ssl_verify):
        """
        Initialization of the Session class.
        The password is intentionally not stored in this class sine we only really need the token

        :param username: The username is stored here so it can be passed easily into other methods in other classes.
        :param cloudurl: Stores the FQDN of the vRealize Automation server
        :param tenant: Stores the tenant to log into. If left blank it will default to vsphere.local
        :param auth_header: Stores the actual Bearer token to be used in subsequent requests.
        :return:
        """
        self.username = username
        self.cloudurl = cloudurl
        self.tenant = tenant
        self.token = auth_header
        self.headers = {'Content-type': 'application/json',
                        'Accept': 'text/plain',
                        'Authorization': self.token}
        self.ssl_verify = ssl_verify

    @classmethod
    def login(cls, username, password, cloudurl, tenant=None, ssl_verify=True):
        """
        Takes in a username, password, URL, and tenant to access a vRealize Automation server AP. These attributes
        can be used to send or retrieve data from the vRealize automation API.

        Basic usage:

        vra = vralib.Session.login(username, password, cloudurl, tenant, ssl_verify=False)

        This creates a Session object called 'vra' which can now be used to access all of the methods in this class.

        :param username: A username@domain with sufficient rights to use the API
        :param password: The password of the user
        :param cloudurl: The vRealize automation server. Should be the FQDN.
        :param tenant: the tenant ID to be logged into. If left empty it will default to vsphere.local
        :param ssl_verify: Enable or disable SSL verification.
        :return: Returns a class that includes all of the login session data (token, tenant and SSL verification)



        """
        # TODO create better exception handling here for when you pass a bad password

        if not tenant:
            tenant = 'vsphere.local'

        try:
            if not ssl_verify:
                try:
                    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
                except AttributeError:
                    pass
            r = requests.post(
                url='https://' + cloudurl + '/identity/api/tokens',
                headers={'Content-type': 'application/json',
                         'Accept': 'text/plain'},
                verify=ssl_verify,
                data=json.dumps({
                    "tenant": tenant,
                    "username": username,
                    "password": password
                })
            )

            vratoken = json.loads(r.content)

            if 'id' in vratoken.keys():
                auth_header = 'Bearer ' + vratoken['id']
                return cls(username, cloudurl, tenant, auth_header, ssl_verify)
            else:
                raise exceptions.InvalidToken('No bearer token found in response. Response was:',
                                              json.dumps(vratoken))

        except requests.exceptions.ConnectionError as e:
            print 'Unable to connect to server %s' % cloudurl
            print 'Exception was ' + str(e)
            exit()

        except requests.exceptions.HTTPError as e:
            print e.response.status_code

    def _request(self, url, request_method='GET', payload=None, **kwargs):
        url = url

        if request_method == "PUT" or "POST" and payload:
            if type(payload) == dict:
                payload = json.dumps(payload)

            r = requests.request(request_method,
                                 url=url,
                                 headers=self.headers,
                                 verify=self.ssl_verify,
                                 data=payload)

            return r.content

        elif request_method == "GET":
            r = requests.request(request_method,
                                 url=url,
                                 headers=self.headers,
                                 verify=self.ssl_verify)
            return json.loads(r.content)

    def get_business_groups(self):
        """

        Will retrieve a list of all vRA business groups for the currently logged in tenant

        :return: python dictionary with the JSON response contents.

        """

        url = 'https://' + self.cloudurl + '/identity/api/tenants/' + self.tenant + '/subtenants'
        return self._request(url)

    def get_entitled_catalog_items(self):
        """

        Retrieves a dictionary of all the currently available catalog items for the logged in user/tenant.
        This can result in multi-page output so I've added some basic pagination here.

        :return: Python dictionary with the JSON response contents from all pages in result['metadata']['totalPages']
        """
        # TODO update the output dict's page number to reflect a list of page numbers iterated through
        # TODO add exception handling for when you're not actually entitled to anything.

        url = 'https://' + self.cloudurl + '/catalog-service/api/consumer/entitledCatalogItems'

        result = self._request(url)

        if result['metadata']['totalPages'] != 1:
            page = 2  # starting on 2 since we've already got page 1's data
            while page <= result['metadata']['totalPages']:
                url = 'https://' + self.cloudurl + '/catalog-service/api/consumer/entitledCatalogItems?page=%s' % page
                next_page = self._request(url)
                for i in next_page['content']:
                    result['content'].append(i)
                page += 1

            return result

        return result

    def get_catalogitem_byname(self, name, catalog=False):
        """

        Loop through catalog items until you find the one with the specified name. This method allows you to "filter"
        returned catalog items via a partial match.

        Basic usage:

        log into vra:

        vra = vralib.Session.login(username, password, cloudurl, tenant, ssl_verify=False)

        catalog_offerings = vra.get_catalogitem_byname(name='cent')

        This will store any catalog items with 'cent' anywhere in the name.

        Optionally this method can be passed an object that includes the catalog:

        vra = vralib.Session.login(username, password, cloudurl, tenant, ssl_verify=False)

        catalog_offerings = vra.get_catalogitem_byname(name='cent', vra.get_get_entitledcatalogitems())

        :param name: A required string that will be used to filter the return to items that contain the string.
        :param catalog: An optional dictionary of all of the catalog items available to the user.
        :return: Returns a list of dictionaries that contain the catalog item and ID
        """

        # TODO probably remove the note below
        # TODO determine what other data may be desired in the return output

        if not catalog:
            catalog = self.get_entitled_catalog_items()

        result = []
        for i in catalog['content']:
            target = i['catalogItem']['name']
            if name.lower() in target.lower():
                element = {'name': i['catalogItem']['name'], 'id': i['catalogItem']['id']}
                result.append(element)

        return result

    def update_request_template(self, catalogitem):
        template = self.get_request_template(catalogitem)
        template = json.loads(template)
        template["data"]["kpsc.Role.Linux.WebServer"] = "nginx"

        return template

    def get_request_template(self, catalogitem):
        url = 'https://' + self.cloudurl + '/catalog-service/api/consumer/entitledCatalogItems/' + catalogitem + '/requests/template'
        return self._request(url)

    def request_item(self, catalogitem, payload=False):
        """

        Allows you to request an item from the vRealize catalog.

        Basic usage:

        Log into vra:
        vra = vralib.Session.login(username, password, cloudurl, tenant, ssl_verify=False)

        Submit a unique id to the method:

        build = vra.request_item('0ebbcf20-abdf-4663-a40c-1e50e7340190')

        There is an optional payload argument. Use this whenever you need to modify the request template prior to submission.

        For example you may opt to change the description of the catalog item with:

        payload = vra.get_request_template('0ebbcf20-abdf-4663-a40c-1e50e7340190')
        payload['description'] = 'My API test!'

        build = vra.request_item('0ebbcf20-abdf-4663-a40c-1e50e7340190', payload)

        See the docstring for the self.get_request_template() method for additional information

        :param catalogitem: A string that includes the unique ID of the catalog item to be provisioned
        :param payload: An optional parameter that should be a dictionary of the catalog request template which can be retrieved via the self.get_request_template method()
        :return: A python dictionary that includes the output from POST operation.

        """

        # TODO should make sure we can modify catalog item beforehand

        if not payload:
            payload = self.get_request_template(catalogitem)

        url = 'https://' + self.cloudurl + '/catalog-service/api/consumer/entitledCatalogItems/' + catalogitem + '/requests'
        return self._request(url, request_method="POST", payload=payload)

    def get_eventbroker_events(self):
        """
        pick a page
        https://jupiter.kpsc.lan/event-broker-service/api/events?page=210

        put newest events first in the response
        https://jupiter.kpsc.lan/event-broker-service/api/events?$orderby=timeStamp desc

        API Docs here:
        vrealize-automation-70-rest-api-docs%20/docs/event-broker-server-war/api/docs/resource_Consumer%20APIs.html

        Some examples of stuff to work with:
          "metadata": {
            "size": 20,
            "totalElements": 4193,
            "totalPages": 210,
            "number": 210,
            "offset": 4180
          }
        ?page=1

        :param vra_session:
        :return:
        """
        # TODO create a handler for the different API verbs this thing needs to support

        url = 'https://' + self.cloudurl + '/event-broker-service/api/events'
        return self._request(url)

    def get_requests(self, id):
        """
        gets a list of all request unless an id is specified. In that case it will only return the request specified.

        param id:
        :return:
        """

        if not id:
            url = 'https://' + self.cloudurl + '/catalog-service/api/consumer/requests'
            return self._request(url)

        url = 'https://' + self.cloudurl + '/catalog-service/api/consumer/requests/' + id
        return self._request(url)

    def get_requests_forms_details(self, id):
        """
        gets some request details on an individual request. may exclude later.

        :return:
        """

        url = 'https://' + self.cloudurl + '/catalog-service/api/consumer/requests/' + id
        return self._request(url)

    def get_request_details(self, id):
        """
        Returns details about a given request. Currently looks identical to output from get_requests_forms_details() method.

        :param id:
        :return:
        """
        url = 'https://' + self.cloudurl + '/catalog-service/api/consumer/requests/' + id + '/resourceViews'
        return self._request(url)

    def get_consumer_resources(self):
        """
        Gets a list of all the provisioned items out there

        :return:
        """
        # TODO add pagination support
        # TODO update metadata field appropriately

        url = 'https://' + self.cloudurl + '/catalog-service/api/consumer/resources'
        result = self._request(url)

        if result['metadata']['totalPages'] != 1:
            page = 2  # starting on 2 since we've already got page 1's data
            while page <= result['metadata']['totalPages']:
                url = 'https://' + self.cloudurl + '/catalog-service/api/consumer/resources?page=%s' % page
                next_page = self._request(url)
                for i in next_page['content']:
                    result['content'].append(i)
                page += 1
            return result

        return result

    def get_storage_reservations(self):
        url = 'https://' + self.cloudurl + '/reservation-service/api/reservations/info'
        return self._request(url)