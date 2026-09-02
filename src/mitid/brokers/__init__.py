"""Identity brokers that sit between a service and MitID.

MitID never talks to a service directly. A broker does: it starts the
authentication session, hands the browser the `aux` blob that mitid.authenticate
needs, and exchanges the resulting authorisation code for whatever the service
recognises as a login. Every Danish site that accepts MitID uses one - NemLog-in
for the public sector, Signicat and Nets for most banks - and which one it is,
is the only part of a login that differs between services.
"""
